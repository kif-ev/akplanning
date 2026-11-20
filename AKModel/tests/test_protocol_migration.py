import socket
from unittest.mock import MagicMock, patch

import requests
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import override_settings, TestCase
from django.urls import reverse

from AKModel.models import AK
from AKModel.protocol_migration import convert_to_mediawiki, download_protocol, fetch_public, \
    get_hedgedoc_download_url, get_wiki_page_title, MediaWikiClient, migrate_protocol, migrate_protocols, \
    MigrationError, MigrationResult, MigrationStatus, PinnedAddressAdapter, resolve_public_address
from AKModel.views.ak import AKMigrateProtocolsView

WIKI = {"api_url": "https://wiki.example.com/w/api.php"}
WIKI_USERNAME = "Bot@AKPlanning"
WIKI_PASSWORD = "secret"
MIGRATION_SETTINGS = {
    "PROTOCOL_MIGRATION_WIKIS": {"wiki.example.com": WIKI},
    "PROTOCOL_MIGRATION_WIKI_CREDENTIALS": {WIKI["api_url"]: {"username": WIKI_USERNAME, "password": WIKI_PASSWORD}},
}


@override_settings(**MIGRATION_SETTINGS)
class ProtocolMigrationLinkTests(TestCase):
    """
    Test parsing of HedgeDoc and wiki links
    """

    def test_hedgedoc_download_url(self):
        """
        Test that note links (on any instance) are translated to download links and other links are rejected
        """
        valid = {
            "https://md.example.com/abc123": "https://md.example.com/abc123/download",
            "https://md.example.com/abc123?both#heading": "https://md.example.com/abc123/download",
            "https://md.example.com/abc123/": "https://md.example.com/abc123/download",
            "https://md.example.com/abc123/download": "https://md.example.com/abc123/download",
            "https://pad.OTHER.org:443/abc123": "https://pad.other.org/abc123/download",
            "https://[2001:db8::1]/abc123": "https://[2001:db8::1]/abc123/download",
        }
        for link, expected in valid.items():
            self.assertEqual(get_hedgedoc_download_url(link), expected, link)

        invalid = ["https://md.example.com/", "https://md.example.com/s/abc123", "https://md.example.com/new",
                   "ftp://md.example.com/abc123", "not a link", "https:///abc123",
                   # The server downloads from these links, hence only https on the default port without credentials
                   "http://md.example.com/abc123", "https://md.example.com:6379/abc123",
                   "https://md.example.com:99999/abc123", "https://user:pw@md.example.com/abc123",
                   "https://user@md.example.com/abc123"]
        for link in invalid:
            self.assertIsNone(get_hedgedoc_download_url(link), link)

    def test_wiki_page_title(self):
        """
        Test that wiki links are translated to page titles and other links are rejected
        """
        valid = {
            "https://wiki.example.com/wiki/KIF42:Test_AK": "KIF42:Test AK",
            "https://wiki.example.com/wiki/KIF42:%C3%84K": "KIF42:ÄK",
            "https://wiki.example.com/w/index.php?title=KIF42:Test_AK&action=edit": "KIF42:Test AK",
        }
        for link, expected in valid.items():
            self.assertEqual(get_wiki_page_title(link), (WIKI, expected), link)

        # Links to the script path must also work if the article path is a prefix of it
        root_wiki = {**WIKI, "article_path": "/"}
        with self.settings(PROTOCOL_MIGRATION_WIKIS={"Wiki.Example.com": root_wiki}):
            self.assertEqual(get_wiki_page_title("https://wiki.example.com/w/index.php?title=KIF42:Test_AK"),
                             (root_wiki, "KIF42:Test AK"))
            self.assertEqual(get_wiki_page_title("https://wiki.example.com/KIF42:Test_AK"),
                             (root_wiki, "KIF42:Test AK"))
            # Script paths without title parameter do not point to a page
            self.assertIsNone(get_wiki_page_title("https://wiki.example.com/w/index.php?curid=123"))

        invalid = ["https://wiki.other.com/wiki/Test", "https://wiki.example.com/wiki/", "https://wiki.example.com/"]
        for link in invalid:
            self.assertIsNone(get_wiki_page_title(link), link)


@override_settings(**MIGRATION_SETTINGS)
class ProtocolMigrationTests(TestCase):
    """
    Test the migration of single protocols with mocked HedgeDoc, pandoc and wiki
    """
    fixtures = ["model.json"]

    def setUp(self):
        self.ak = AK.objects.get(pk=1)
        self.ak.protocol_link = "https://md.example.com/abc123"
        self.ak.link = "https://wiki.example.com/wiki/KIF42:Test_AK"
        download_patcher = patch("AKModel.protocol_migration.download_protocol", return_value="# Protocol")
        self.download = download_patcher.start()
        self.addCleanup(download_patcher.stop)
        self.client_mock = MagicMock(spec=MediaWikiClient)
        self.client_mock.get_page.return_value = (False, "", None, "2026-01-02T00:00:00Z")
        self.wiki_clients = {WIKI["api_url"]: self.client_mock}

    def _migrate(self):
        with patch("AKModel.protocol_migration.convert_to_mediawiki", return_value="= Protocol =") as convert:
            result = migrate_protocol(self.ak, self.wiki_clients)
        return result, convert

    def test_success_missing_page(self):
        """
        Test migration to a page that does not exist yet
        """
        result, convert = self._migrate()
        self.assertEqual(result.status, MigrationStatus.SUCCESS)
        self.download.assert_called_once_with("https://md.example.com/abc123/download")
        convert.assert_called_once_with("# Protocol")
        self.client_mock.write_page.assert_called_once()
        args, kwargs = self.client_mock.write_page.call_args
        self.assertEqual(args, ("KIF42:Test AK", "= Protocol ="))
        self.assertFalse(kwargs["exists"])

    def test_success_empty_page(self):
        """
        Test migration to an existing but empty page
        """
        self.client_mock.get_page.return_value = (True, "  \n", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
        result, _ = self._migrate()
        self.assertEqual(result.status, MigrationStatus.SUCCESS)
        kwargs = self.client_mock.write_page.call_args.kwargs
        self.assertTrue(kwargs["exists"])
        self.assertEqual(kwargs["base_timestamp"], "2026-01-01T00:00:00Z")
        self.assertEqual(kwargs["start_timestamp"], "2026-01-02T00:00:00Z")

    def test_page_not_empty(self):
        """
        Test that non-empty pages are not touched
        """
        self.client_mock.get_page.return_value = (True, "Some content", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
        result, convert = self._migrate()
        self.assertEqual(result.status, MigrationStatus.WIKI_PAGE_NOT_EMPTY)
        convert.assert_not_called()
        self.client_mock.write_page.assert_not_called()

    def test_invalid_links(self):
        """
        Test that missing or invalid links are reported without contacting any service
        """
        cases = [
            ("", self.ak.link, MigrationStatus.NO_PROTOCOL_LINK),
            ("http://md.example.com/abc", self.ak.link, MigrationStatus.INVALID_PROTOCOL_LINK),
            (self.ak.protocol_link, "", MigrationStatus.NO_WIKI_LINK),
            (self.ak.protocol_link, "https://wiki.other.com/wiki/Test", MigrationStatus.INVALID_WIKI_LINK),
        ]
        for protocol_link, link, expected in cases:
            self.ak.protocol_link = protocol_link
            self.ak.link = link
            result, _ = self._migrate()
            self.assertEqual(result.status, expected)
        self.download.assert_not_called()
        self.client_mock.get_page.assert_not_called()

    def test_download_failed(self):
        """
        Test handling of notes that cannot be downloaded (e.g., redirect to login)
        """
        self.download.side_effect = MigrationError(MigrationStatus.PROTOCOL_DOWNLOAD_FAILED, "HTTP 404")
        result, _ = self._migrate()
        self.assertEqual(result.status, MigrationStatus.PROTOCOL_DOWNLOAD_FAILED)
        self.client_mock.write_page.assert_not_called()

    def test_empty_protocol(self):
        """
        Test that empty protocols are not written to the wiki
        """
        self.download.return_value = "\n"
        result, _ = self._migrate()
        self.assertEqual(result.status, MigrationStatus.PROTOCOL_EMPTY)
        self.client_mock.write_page.assert_not_called()

    def test_wiki_error(self):
        """
        Test handling of errors when writing to the wiki (e.g., edit conflicts)
        """
        self.client_mock.write_page.side_effect = MigrationError(MigrationStatus.WIKI_ERROR, "articleexists")
        result, _ = self._migrate()
        self.assertEqual(result.status, MigrationStatus.WIKI_ERROR)
        self.assertEqual(result.detail, "articleexists")

    def test_unexpected_error(self):
        """
        Test that unexpected errors are reported for the AK instead of aborting the whole migration
        """
        self.client_mock.write_page.side_effect = KeyError("edit")
        with self.assertLogs("AKModel.protocol_migration", level="ERROR"):
            result, _ = self._migrate()
        self.assertEqual(result.status, MigrationStatus.UNEXPECTED_ERROR)
        self.assertEqual(result.detail, "KeyError: 'edit'")


def hedgedoc_response(status_code=200, content=None, content_type="text/markdown; charset=UTF-8", location=None):
    """
    Create a mocked (streamed) response of HedgeDoc

    :param content: list of chunks of the body or an exception to raise when reading it
    """
    response = MagicMock(status_code=status_code, headers={"Content-Type": content_type})
    if location is not None:
        response.headers["Location"] = location
    if content is None:
        content = ["# Protokoll äöü".encode()]
    if isinstance(content, Exception):
        response.iter_content.side_effect = content
    else:
        response.iter_content.return_value = content
    return response


def api_response(data, status_code=200):
    """
    Create a mocked response of the MediaWiki API
    """
    response = MagicMock(status_code=status_code)
    response.json.return_value = data
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status_code}")
    return response


def token_response(token_type, token):
    """
    Create a mocked response of the MediaWiki API to a token query
    """
    return api_response({"query": {"tokens": {f"{token_type}token": token}}})


class MediaWikiClientTests(TestCase):
    """
    Test the MediaWiki API client with a mocked HTTP session
    """

    def setUp(self):
        cache.clear()
        self.client_ = MediaWikiClient(WIKI, username=WIKI_USERNAME, password=WIKI_PASSWORD)
        # Most tests do not care about the login, see test_login for that
        self.client_.csrf_token = "CSRF"
        self.client_.session = MagicMock()
        self.get = self.client_.session.get
        self.post = self.client_.session.post

    def test_get_page_existing(self):
        """
        Test retrieving content and timestamp of an existing page
        """
        self.get.return_value = api_response({"curtimestamp": "2026-01-02T00:00:00Z", "query": {"pages": [
            {"title": "Test", "revisions": [
                {"timestamp": "2026-01-01T00:00:00Z", "slots": {"main": {"content": "Content"}}}]}]}})
        self.assertEqual(self.client_.get_page("Test"),
                         (True, "Content", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"))
        params = self.get.call_args.kwargs["params"]
        self.assertEqual(params["titles"], "Test")
        self.assertEqual(params["curtimestamp"], "1")
        self.assertEqual(params["format"], "json")
        self.assertEqual(params["formatversion"], "2")

    def test_get_page_missing(self):
        """
        Test retrieving a page that does not exist
        """
        self.get.return_value = api_response({"curtimestamp": "2026-01-02T00:00:00Z",
                                              "query": {"pages": [{"title": "Test", "missing": True}]}})
        self.assertEqual(self.client_.get_page("Test"), (False, "", None, "2026-01-02T00:00:00Z"))

    def test_get_page_login(self):
        """
        Test that the login is performed before reading (wikis may require it for reading)
        """
        self.client_.csrf_token = None
        self.get.side_effect = [token_response("login", "LOGIN"), token_response("csrf", "CSRF"),
                                api_response({"query": {"pages": [{"title": "Test", "missing": True}]}})]
        self.post.return_value = api_response({"login": {"result": "Success"}})
        self.client_.get_page("Test")
        self.assertEqual(self.post.call_args.kwargs["data"]["action"], "login")
        self.assertEqual(self.get.call_args.kwargs["params"]["titles"], "Test")

    def test_get_page_invalid_title(self):
        """
        Test that invalid titles are reported as invalid wiki links
        """
        self.get.return_value = api_response({"query": {"pages": [
            {"title": "Bad[", "invalid": True, "invalidreason": "invalid characters"}]}})
        with self.assertRaises(MigrationError) as cm:
            self.client_.get_page("Bad[")
        self.assertEqual(cm.exception.status, MigrationStatus.INVALID_WIKI_LINK)
        self.assertEqual(cm.exception.detail, "invalid characters")

    def test_get_page_not_regular(self):
        """
        Test that special pages and interwiki titles are reported as invalid wiki links
        """
        responses = {
            "Special:RecentChanges": {"query": {"pages": [
                {"title": "Special:RecentChanges", "ns": -1, "special": True}]}},
            "en:Test": {"query": {"interwiki": [{"title": "en:Test", "iw": "en"}]}},
        }
        for title, response in responses.items():
            with self.subTest(title=title):
                self.get.return_value = api_response(response)
                with self.assertRaises(MigrationError) as cm:
                    self.client_.get_page(title)
                self.assertEqual(cm.exception.status, MigrationStatus.INVALID_WIKI_LINK)

    def test_get_page_unexpected_response(self):
        """
        Test that a page without revisions is reported as wiki error
        """
        self.get.return_value = api_response({"query": {"pages": [{"title": "Test"}]}})
        with self.assertRaises(MigrationError) as cm:
            self.client_.get_page("Test")
        self.assertEqual(cm.exception.status, MigrationStatus.WIKI_ERROR)

    def test_request_errors(self):
        """
        Test that network errors, HTTP errors, API errors and invalid responses are reported as wiki errors
        """
        invalid_json = MagicMock(status_code=200)
        invalid_json.json.side_effect = ValueError("no json")
        cases = [
            requests.ConnectionError("unreachable"),
            api_response({}, status_code=500),
            api_response({"error": {"code": "readapidenied", "info": "no read permission"}}),
            invalid_json,
        ]
        for case in cases:
            if isinstance(case, Exception):
                self.get.side_effect = case
            else:
                self.get.side_effect = None
                self.get.return_value = case
            with self.assertRaises(MigrationError) as cm:
                self.client_.get_page("Test")
            self.assertEqual(cm.exception.status, MigrationStatus.WIKI_ERROR)

    def test_login(self):
        """
        Test login with bot password and retrieval of csrf token
        """
        self.client_.csrf_token = None
        self.get.side_effect = [token_response("login", "LOGIN"), token_response("csrf", "CSRF")]
        self.post.return_value = api_response({"login": {"result": "Success"}})
        self.client_.login()
        self.assertEqual(self.client_.csrf_token, "CSRF")
        data = self.post.call_args.kwargs["data"]
        self.assertEqual(data["action"], "login")
        self.assertEqual(data["lgname"], WIKI_USERNAME)
        self.assertEqual(data["lgpassword"], WIKI_PASSWORD)
        self.assertEqual(data["lgtoken"], "LOGIN")

        # Login should only be performed once
        self.client_.login()
        self.assertEqual(self.get.call_count, 2)
        self.assertEqual(self.post.call_count, 1)

    def test_login_cached(self):
        """
        Test that logins are stored in the cache and reused by new clients (e.g., in the next request)
        """
        self.client_.csrf_token = None
        self.client_.session = requests.Session()
        with patch.object(self.client_.session, "get") as get, patch.object(self.client_.session, "post") as post:
            get.side_effect = [token_response("login", "LOGIN"), token_response("csrf", "CSRF")]
            post.return_value = api_response({"login": {"result": "Success"}})
            self.client_.session.cookies.set("wiki_session", "abc")
            self.client_.login()

        client = MediaWikiClient(WIKI, username=WIKI_USERNAME, password=WIKI_PASSWORD)
        client.restore_session()
        self.assertEqual(client.csrf_token, "CSRF")
        self.assertEqual(client.session.cookies.get("wiki_session"), "abc")

        # Logins of other users must not be reused
        other = MediaWikiClient(WIKI, username="Other@AKPlanning")
        other.restore_session()
        self.assertIsNone(other.csrf_token)

    def test_login_expired(self):
        """
        Test that expired (e.g., cached) logins are detected and renewed
        """
        self.get.side_effect = [
            api_response({"error": {"code": "assertuserfailed", "info": "not logged in"}}),
            token_response("login", "LOGIN"), token_response("csrf", "NEW"),
            api_response({"query": {"pages": [{"title": "Test", "missing": True}]}}),
        ]
        self.post.return_value = api_response({"login": {"result": "Success"}})
        self.assertFalse(self.client_.get_page("Test")[0])
        self.assertEqual(self.client_.csrf_token, "NEW")
        self.assertEqual(self.get.call_args_list[0].kwargs["params"]["assert"], "user")
        self.assertEqual(self.get.call_args.kwargs["params"]["titles"], "Test")

        # A stale token is replaced when retrying an edit
        self.get.side_effect = [token_response("login", "LOGIN"), token_response("csrf", "NEWER")]
        self.post.side_effect = [api_response({"error": {"code": "badtoken", "info": "invalid token"}}),
                                 api_response({"login": {"result": "Success"}}),
                                 api_response({"edit": {"result": "Success"}})]
        self.client_.write_page("Test", "= Content =", "Summary", exists=False, base_timestamp=None,
                                start_timestamp=None)
        self.assertEqual(self.post.call_args.kwargs["data"]["token"], "NEWER")

        # Retry only once
        self.get.side_effect = [token_response("login", "LOGIN"), token_response("csrf", "CSRF")]
        self.post.side_effect = [api_response({"error": {"code": "badtoken", "info": "invalid token"}}),
                                 api_response({"login": {"result": "Success"}}),
                                 api_response({"error": {"code": "badtoken", "info": "invalid token"}})]
        with self.assertRaises(MigrationError):
            self.client_.write_page("Test", "= Content =", "Summary", exists=False, base_timestamp=None,
                                    start_timestamp=None)

    def test_login_failed(self):
        """
        Test that a failed login is reported and no token is stored
        """
        self.client_.csrf_token = None
        self.get.return_value = token_response("login", "LOGIN")
        self.post.return_value = api_response({"login": {"result": "Failed", "reason": "Wrong password"}})
        with self.assertRaises(MigrationError) as cm:
            self.client_.login()
        self.assertEqual(cm.exception.status, MigrationStatus.WIKI_ERROR)
        self.assertIn("Wrong password", cm.exception.detail)
        self.assertIsNone(self.client_.csrf_token)

    def test_anonymous(self):
        """
        Test that no login is performed when no credentials are configured
        """
        client = MediaWikiClient({"api_url": WIKI["api_url"]})
        client.session = MagicMock()
        client.session.get.return_value = token_response("csrf", "CSRF")
        client.login()
        self.assertEqual(client.csrf_token, "CSRF")
        client.session.post.assert_not_called()

    def test_write_missing_page(self):
        """
        Test that missing pages are only created, never overwritten
        """
        self.client_.csrf_token = "CSRF"
        self.post.return_value = api_response({"edit": {"result": "Success"}})
        self.client_.write_page("Test", "= Content =", "Summary", exists=False, base_timestamp=None,
                                start_timestamp="2026-01-02T00:00:00Z")
        data = self.post.call_args.kwargs["data"]
        self.assertEqual(data["action"], "edit")
        self.assertEqual(data["title"], "Test")
        self.assertEqual(data["text"], "= Content =")
        self.assertEqual(data["summary"], "Summary")
        self.assertEqual(data["token"], "CSRF")
        self.assertEqual(data["createonly"], "1")
        self.assertNotIn("nocreate", data)

    def test_write_empty_page(self):
        """
        Test that existing empty pages are edited with edit conflict detection
        """
        self.client_.csrf_token = "CSRF"
        self.post.return_value = api_response({"edit": {"result": "Success"}})
        self.client_.write_page("Test", "= Content =", "Summary", exists=True, base_timestamp="2026-01-01T00:00:00Z",
                                start_timestamp="2026-01-02T00:00:00Z")
        data = self.post.call_args.kwargs["data"]
        self.assertEqual(data["nocreate"], "1")
        self.assertEqual(data["basetimestamp"], "2026-01-01T00:00:00Z")
        self.assertEqual(data["starttimestamp"], "2026-01-02T00:00:00Z")
        self.assertNotIn("createonly", data)

    def test_write_conflict(self):
        """
        Test that pages created in the meantime (edit conflict) are reported as errors
        """
        self.client_.csrf_token = "CSRF"
        self.post.return_value = api_response({"error": {"code": "articleexists", "info": "already exists"}})
        with self.assertRaises(MigrationError) as cm:
            self.client_.write_page("Test", "= Content =", "Summary", exists=False, base_timestamp=None,
                                    start_timestamp="2026-01-02T00:00:00Z")
        self.assertEqual(cm.exception.status, MigrationStatus.WIKI_ERROR)
        self.assertIn("articleexists", cm.exception.detail)

    def test_write_not_successful(self):
        """
        Test that unsuccessful edits without API error (e.g., captcha or abuse filter) are reported
        """
        self.client_.csrf_token = "CSRF"
        self.post.return_value = api_response({"edit": {"result": "Failure", "captcha": {}}})
        with self.assertRaises(MigrationError) as cm:
            self.client_.write_page("Test", "= Content =", "Summary", exists=False, base_timestamp=None,
                                    start_timestamp="2026-01-02T00:00:00Z")
        self.assertEqual(cm.exception.status, MigrationStatus.WIKI_ERROR)


@override_settings(**MIGRATION_SETTINGS)
class ProtocolDownloadAndConversionTests(TestCase):
    """
    Test downloading protocols from HedgeDoc and converting them using pandoc (via pypandoc)
    """

    def test_download(self):
        """
        Test successful download (decoded as UTF-8)
        """
        with patch("AKModel.protocol_migration.fetch_public", return_value=hedgedoc_response()) as fetch:
            self.assertEqual(download_protocol("https://md.example.com/abc/download"), "# Protokoll äöü")
        fetch.assert_called_once_with("https://md.example.com/abc/download")
        # The (streamed) response must be closed
        fetch.return_value.__exit__.assert_called_once()

    def test_download_failed(self):
        """
        Test that HTTP errors, redirects (e.g., to login), network errors and other content are reported
        """
        for status_code in [302, 403, 404, 500]:
            with patch("AKModel.protocol_migration.fetch_public",
                       return_value=hedgedoc_response(status_code, location="https://md.example.com/login")):
                with self.assertRaises(MigrationError) as cm:
                    download_protocol("https://md.example.com/abc/download")
            self.assertEqual(cm.exception.status, MigrationStatus.PROTOCOL_DOWNLOAD_FAILED)
            self.assertIn(str(status_code), cm.exception.detail)

        failures = {
            "Not a HedgeDoc note": hedgedoc_response(content_type="text/html"),
            "larger than 5 MB": hedgedoc_response(content=[b"x" * 1024 * 1024] * 6),
            "connection lost": hedgedoc_response(content=requests.ConnectionError("connection lost")),
        }
        for expected, response in failures.items():
            with patch("AKModel.protocol_migration.fetch_public", return_value=response):
                with self.assertRaises(MigrationError) as cm:
                    download_protocol("https://md.example.com/abc/download")
            self.assertEqual(cm.exception.status, MigrationStatus.PROTOCOL_DOWNLOAD_FAILED)
            self.assertIn(expected, cm.exception.detail)

    def test_resolve_public_address(self):
        """
        Test that only hosts with public addresses are accepted
        """

        def addrinfo(*addresses):
            return [(None, None, None, "", (address, 443)) for address in addresses]

        with patch("AKModel.protocol_migration.socket.getaddrinfo",
                   return_value=addrinfo("93.184.216.34", "2606:2800:220:1::1")):
            self.assertEqual(resolve_public_address("md.example.com"), "93.184.216.34")

        for addresses in [("127.0.0.1",), ("10.1.2.3",), ("192.168.0.1",), ("169.254.169.254",), ("::1",),
                          ("fe80::1",), ("fd00::1",), ("::ffff:127.0.0.1",), ("224.0.0.1",), ("0.0.0.0",),
                          ("93.184.216.34", "127.0.0.1")]:
            with patch("AKModel.protocol_migration.socket.getaddrinfo", return_value=addrinfo(*addresses)):
                with self.assertRaises(MigrationError, msg=addresses) as cm:
                    resolve_public_address("md.example.com")
            self.assertEqual(cm.exception.status, MigrationStatus.INVALID_PROTOCOL_LINK)

        with patch("AKModel.protocol_migration.socket.getaddrinfo", side_effect=socket.gaierror("unknown host")):
            with self.assertRaises(MigrationError) as cm:
                resolve_public_address("md.example.com")
        self.assertEqual(cm.exception.status, MigrationStatus.PROTOCOL_DOWNLOAD_FAILED)

    def test_fetch_public(self):
        """
        Test that requests are sent to the checked address while TLS still uses the hostname
        """
        for address, expected_url in [("93.184.216.34", "https://93.184.216.34/abc/download?x=1"),
                                      ("2606:2800:220:1::1", "https://[2606:2800:220:1::1]/abc/download?x=1")]:
            with patch("AKModel.protocol_migration.resolve_public_address", return_value=address) as resolve, \
                    patch.object(requests.Session, "get", autospec=True) as get:
                self.assertEqual(fetch_public("https://md.example.com/abc/download?x=1"), get.return_value)
            resolve.assert_called_once_with("md.example.com")
            session, url = get.call_args.args
            self.assertEqual(url, expected_url)
            self.assertEqual(get.call_args.kwargs["headers"]["Host"], "md.example.com")
            self.assertFalse(get.call_args.kwargs["allow_redirects"])
            adapter = session.get_adapter(url)
            self.assertIsInstance(adapter, PinnedAddressAdapter)
            self.assertEqual(adapter.poolmanager.connection_pool_kw["server_hostname"], "md.example.com")
            self.assertEqual(adapter.poolmanager.connection_pool_kw["assert_hostname"], "md.example.com")

        with patch("AKModel.protocol_migration.resolve_public_address", return_value="93.184.216.34"), \
                patch.object(requests.Session, "get", side_effect=requests.Timeout("timeout")):
            with self.assertRaises(MigrationError) as cm:
                fetch_public("https://md.example.com/abc/download")
        self.assertEqual(cm.exception.status, MigrationStatus.PROTOCOL_DOWNLOAD_FAILED)

    def test_convert(self):
        """
        Test conversion of markdown to MediaWiki syntax using the bundled pandoc
        """
        result = convert_to_mediawiki("# Protokoll\n\n* Punkt **fett** äöü [Link](https://example.com)\n\n"
                                      "| a | b |\n|---|---|\n| 1 | 2 |\n")
        self.assertIn("= Protokoll =", result)
        # MediaWiki generates anchors for headings itself
        self.assertNotIn("<span", result)
        self.assertIn("* Punkt '''fett''' äöü [https://example.com Link]", result)
        self.assertIn('{| class="wikitable"', result)

    def test_download_redirects(self):
        """
        Test that redirects are only followed to download URLs of notes
        """
        redirect = "https://md2.example.com/abc/download"
        with patch("AKModel.protocol_migration.fetch_public",
                   side_effect=[hedgedoc_response(301, location=redirect), hedgedoc_response()]) as fetch:
            self.assertEqual(download_protocol("https://md.example.com/abc/download"), "# Protokoll äöü")
        self.assertEqual(fetch.call_args.args[0], redirect)

        for location in ["https://md.example.com/abc", "/login", "http://md.example.com/abc/download"]:
            with patch("AKModel.protocol_migration.fetch_public",
                       return_value=hedgedoc_response(302, location=location)) as fetch:
                with self.assertRaises(MigrationError) as cm:
                    download_protocol("https://md.example.com/abc/download")
            self.assertEqual(cm.exception.status, MigrationStatus.PROTOCOL_DOWNLOAD_FAILED)
            fetch.assert_called_once()

        with patch("AKModel.protocol_migration.fetch_public",
                   return_value=hedgedoc_response(301, location=redirect)):
            with self.assertRaises(MigrationError) as cm:
                download_protocol("https://md.example.com/abc/download")
        self.assertEqual(cm.exception.detail, "Too many redirects")

    def test_convert_hedgedoc_specifics(self):
        """
        Test that single line breaks are kept and YAML metadata is dropped (as rendered by HedgeDoc)
        """
        result = convert_to_mediawiki("---\ntitle: AK Foo\ntags: [KIF\n---\nAnwesend: A\nB\n\n---\n\nEnde")
        self.assertEqual(result.split("\n")[:2], ["Anwesend: A<br />", "B"])
        self.assertNotIn("title", result)
        self.assertNotIn("tags", result)
        # Horizontal rules later in the protocol must be kept
        self.assertIn("-----", result)

    def test_convert_pandoc_call(self):
        """
        Test that pandoc is called with the right formats and sandboxed
        """
        with patch("AKModel.protocol_migration.pypandoc.convert_text", return_value="= Protokoll =") as convert:
            self.assertEqual(convert_to_mediawiki("# Protokoll"), "= Protokoll =")
        convert.assert_called_once_with("# Protokoll", "mediawiki", format="gfm+hard_line_breaks-gfm_auto_identifiers",
                                        sandbox=True)

    def test_convert_failed(self):
        """
        Test that pandoc errors and a missing pandoc are reported
        """
        for error in [RuntimeError("Pandoc died with exitcode \"64\"\n"), OSError("No pandoc was found")]:
            with patch("AKModel.protocol_migration.pypandoc.convert_text", side_effect=error):
                with self.assertRaises(MigrationError) as cm:
                    convert_to_mediawiki("# Protokoll")
            self.assertEqual(cm.exception.status, MigrationStatus.CONVERSION_FAILED)
            self.assertEqual(cm.exception.detail, str(error).strip())


@override_settings(**MIGRATION_SETTINGS)
class MigrateProtocolsTests(TestCase):
    """
    Test the migration of multiple protocols
    """
    fixtures = ["model.json"]

    def test_wiki_client_reused(self):
        """
        Test that one wiki client (and hence one login) is used for all AKs on the same wiki
        and that results are returned in the order of the AKs
        """
        aks = list(AK.objects.filter(pk__in=[1, 2]).order_by("pk"))
        for ak in aks:
            ak.protocol_link = f"https://md.example.com/note{ak.pk}"
            ak.link = f"https://wiki.example.com/wiki/Page_{ak.pk}"

        with patch("AKModel.protocol_migration.MediaWikiClient") as client_class, \
                patch("AKModel.protocol_migration.download_protocol", return_value="# Protocol"), \
                patch("AKModel.protocol_migration.convert_to_mediawiki", return_value="= Protocol ="):
            client_class.return_value.get_page.return_value = (False, "", None, "2026-01-02T00:00:00Z")
            results = migrate_protocols(aks)

        client_class.assert_called_once_with(WIKI, username=WIKI_USERNAME, password=WIKI_PASSWORD)
        self.assertEqual([r.ak for r in results], aks)
        self.assertTrue(all(r.success for r in results))
        titles = [c.args[0] for c in client_class.return_value.write_page.call_args_list]
        self.assertEqual(titles, ["Page 1", "Page 2"])


@override_settings(**MIGRATION_SETTINGS)
class ProtocolMigrationViewTests(TestCase):
    """
    Test the admin action and views for protocol migration
    """
    fixtures = ["model.json"]

    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create(username="Test Admin User", is_staff=True,
                                                    is_superuser=True, is_active=True)
        self.normal_user = user_model.objects.create(username="Test Normal User", is_staff=False, is_active=True)
        self.url = reverse("admin:ak-migrate-protocols") + "?pks=1,2"

    def test_admin_action(self):
        """
        Test that the admin action redirects to the confirmation view with the selected AKs
        """
        self.client.force_login(self.admin_user)
        response = self.client.post(reverse("admin:AKModel_ak_changelist"),
                                    {"action": "migrate_protocols", "_selected_action": [1, 2]})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)

    def test_confirmation(self):
        """
        Test that the confirmation page renders and lists the AKs with their links
        """
        ak = AK.objects.get(pk=1)
        ak.protocol_link = "https://md.example.com/abc123"
        ak.save()

        self.client.force_login(self.admin_user)
        with patch("AKModel.views.ak.migrate_protocols") as migrate:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/AKModel/action_intermediate.html")
        self.assertIn(f"{ak}: https://md.example.com/abc123 → {ak.link}", response.context["preview"])
        self.assertIn(str(AK.objects.get(pk=2)), response.context["preview"])
        # Nothing should happen before confirmation
        migrate.assert_not_called()

    def test_result(self):
        """
        Test that the report page lists the AKs with one migration URL each but does not migrate anything itself
        """
        self.client.force_login(self.admin_user)
        with patch("AKModel.views.ak.migrate_protocols") as migrate:
            response = self.client.post(self.url, {"pks": "1,2"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/AKModel/protocol_migration_result.html")
        self.assertEqual(response.context["title"], AKMigrateProtocolsView.title)
        self.assertEqual(list(response.context["aks"]), list(AK.objects.filter(pk__in=[1, 2]).order_by("pk")))
        for pk in [1, 2]:
            self.assertContains(response, f'data-url="{reverse("admin:ak-migrate-protocol", args=[pk])}"')
        # The migration is triggered AK by AK from the report page
        migrate.assert_not_called()

    def test_migrate_single(self):
        """
        Test the migration of a single AK triggered from the report page
        """
        ak = AK.objects.get(pk=1)
        url = reverse("admin:ak-migrate-protocol", args=[ak.pk])
        self.client.force_login(self.admin_user)

        result = MigrationResult(ak, MigrationStatus.WIKI_PAGE_NOT_EMPTY, "https://wiki.example.com/wiki/X")
        with patch("AKModel.views.ak.migrate_protocols", return_value=[result]) as migrate:
            response = self.client.post(url)
        self.assertEqual(list(migrate.call_args.args[0]), [ak])
        self.assertEqual(response.json(), {
            "status": "wiki_page_not_empty",
            "label": str(MigrationStatus.WIKI_PAGE_NOT_EMPTY.label),
            "success": False,
            "detail": "https://wiki.example.com/wiki/X",
        })
        # Nothing was written to the wiki, hence nothing should be logged
        self.assertFalse(LogEntry.objects.exists())

        result = MigrationResult(ak, MigrationStatus.SUCCESS, ak.link)
        with patch("AKModel.views.ak.migrate_protocols", return_value=[result]):
            response = self.client.post(url)
        self.assertTrue(response.json()["success"])
        entry = LogEntry.objects.get()
        self.assertEqual(entry.object_id, str(ak.pk))
        self.assertEqual(entry.user, self.admin_user)
        self.assertEqual(entry.action_flag, CHANGE)

    def test_migrate_single_errors(self):
        """
        Test that the single migration only accepts POST requests for existing AKs
        """
        self.client.force_login(self.admin_user)
        with patch("AKModel.views.ak.migrate_protocols") as migrate:
            self.assertEqual(self.client.get(reverse("admin:ak-migrate-protocol", args=[1])).status_code, 405)
            self.assertEqual(self.client.post(reverse("admin:ak-migrate-protocol", args=[9999])).status_code, 404)
        migrate.assert_not_called()

    def test_change_permission_required(self):
        """
        Test that staff users without permission to change AKs can neither see the action nor migrate protocols
        """
        user_model = get_user_model()
        staff_user = user_model.objects.create(username="Test Staff User", is_staff=True, is_active=True)
        staff_user.user_permissions.add(Permission.objects.get(codename="view_ak"))
        self.client.force_login(staff_user)

        response = self.client.get(reverse("admin:AKModel_ak_changelist"))
        self.assertNotIn("migrate_protocols", dict(response.context["action_form"].fields["action"].choices))
        with patch("AKModel.views.ak.migrate_protocols") as migrate:
            for response in [self.client.get(self.url), self.client.post(self.url, {"pks": "1,2"}),
                             self.client.post(reverse("admin:ak-migrate-protocol", args=[1]))]:
                self.assertEqual(response.status_code, 403)
        migrate.assert_not_called()

    def test_action_hidden_without_configuration(self):
        """
        Test that the action is only offered if wikis are configured
        """
        self.client.force_login(self.admin_user)
        changelist = reverse("admin:AKModel_ak_changelist")
        self.assertIn("migrate_protocols", dict(self.client.get(changelist).context["action_form"]
                                                .fields["action"].choices))
        with self.settings(PROTOCOL_MIGRATION_WIKIS={}):
            self.assertNotIn("migrate_protocols", dict(self.client.get(changelist).context["action_form"]
                                                       .fields["action"].choices))

    def test_access_restricted(self):
        """
        Test that anonymous and non-staff users can neither see the view nor trigger a migration
        """
        for user in [None, self.normal_user]:
            self.client.logout()
            if user is not None:
                self.client.force_login(user)
            single_url = reverse("admin:ak-migrate-protocol", args=[1])
            with patch("AKModel.views.ak.migrate_protocols") as migrate:
                for response in [self.client.get(self.url), self.client.post(self.url, {"pks": "1,2"}),
                                 self.client.post(single_url)]:
                    self.assertEqual(response.status_code, 302)
                    self.assertIn(reverse("admin:login"), response["Location"])
            migrate.assert_not_called()
