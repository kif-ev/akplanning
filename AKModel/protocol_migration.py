"""
Migration of AK protocols from HedgeDoc pads to MediaWiki pages

For each AK, the protocol (referenced by ``protocol_link``) is downloaded from HedgeDoc as markdown,
converted to MediaWiki syntax using pandoc (bundled with pypandoc_binary) and written to the wiki page of the AK
(referenced by ``link``), but only if that wiki page is still empty (or does not exist yet).

Protocols may be stored on any HedgeDoc instance. Since protocol links are entered by users, downloads are restricted
to public addresses (see :func:`fetch_public`). Which wikis are supported is configured in the settings, see
``PROTOCOL_MIGRATION_WIKIS`` and ``PROTOCOL_MIGRATION_WIKI_CREDENTIALS``.
"""
import ipaddress
import logging
import pypandoc
import re
import requests
import socket
from dataclasses import dataclass
from django.conf import settings
from django.core.cache import cache
from django.db.models import TextChoices
from django.utils.translation import gettext_lazy as _
from requests.adapters import HTTPAdapter
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit

from AKModel.models import AK

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30
USER_AGENT = "AKPlanning protocol migration"
MAX_REDIRECTS = 5
REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)
# Upper limit for the size of a downloaded protocol (in bytes)
MAX_PROTOCOL_SIZE = 5 * 1024 * 1024
# How long wiki logins are reused across requests (MediaWiki sessions typically last longer)
WIKI_SESSION_CACHE_TIMEOUT = 30 * 60

# YAML metadata at the beginning of a HedgeDoc note (e.g., title, tags), which is not part of the protocol itself
FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.DOTALL)

# Paths of HedgeDoc that do not point to an (editable) note and hence cannot be downloaded as markdown
HEDGEDOC_RESERVED_PATHS = {"s", "p", "new", "features", "login", "logout", "register", "me", "history", "status",
                           "config", "uploads", "auth", "api", "build", "js", "css", "fonts", "docs"}


class MigrationStatus(TextChoices):
    """
    Possible outcomes of the migration of a single AK protocol
    (in the order they should be shown to the user)
    """
    SUCCESS = "success", _("Protocol successfully migrated")
    NO_PROTOCOL_LINK = "no_protocol_link", _("No protocol link")
    INVALID_PROTOCOL_LINK = "invalid_protocol_link", _("Protocol link is not a valid HedgeDoc link")
    PROTOCOL_DOWNLOAD_FAILED = "protocol_download_failed", _("Protocol could not be downloaded from HedgeDoc")
    PROTOCOL_EMPTY = "protocol_empty", _("Protocol is empty")
    CONVERSION_FAILED = "conversion_failed", _("Conversion to MediaWiki syntax failed")
    NO_WIKI_LINK = "no_wiki_link", _("No wiki link")
    INVALID_WIKI_LINK = "invalid_wiki_link", _("Wiki link is not a valid MediaWiki link")
    WIKI_PAGE_NOT_EMPTY = "wiki_page_not_empty", _("Wiki page is not empty")
    WIKI_ERROR = "wiki_error", _("Communication with the wiki failed")
    UNEXPECTED_ERROR = "unexpected_error", _("Unexpected error")


# Outcomes that are not successful but also no failure since there is nothing to migrate
# (no protocol at all, or the wiki page already has content that must not be overwritten)
NOTHING_TO_MIGRATE_STATUSES = {
    MigrationStatus.NO_PROTOCOL_LINK,
    MigrationStatus.PROTOCOL_EMPTY,
    MigrationStatus.WIKI_PAGE_NOT_EMPTY,
}


@dataclass
class MigrationResult:
    """
    Result of the migration of a single AK protocol
    """
    ak: AK
    status: MigrationStatus
    detail: str = ""

    @property
    def success(self) -> bool:
        """
        Was the migration of this protocol successful?
        """
        return self.status == MigrationStatus.SUCCESS


class MigrationError(Exception):
    """
    Raised when the migration of a single protocol cannot be completed
    """

    def __init__(self, status: MigrationStatus, detail: str = ""):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def get_hedgedoc_download_url(protocol_link: str) -> str | None:
    """
    Determine the URL to download the markdown source of a HedgeDoc note

    :param protocol_link: link to the note, e.g., https://md.example.com/abc123?both#heading
    :return: download URL (e.g., https://md.example.com/abc123/download) or None if the link
        cannot point to a HedgeDoc note. Since the server downloads from these links (which are entered by users),
        only https links on the default port and without credentials are accepted
    """
    parts = urlsplit(protocol_link.strip())
    try:
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or port not in (None, 443) \
            or parts.username is not None or parts.password is not None:
        return None
    segments = [s for s in parts.path.split("/") if s != ""]
    # Allow links pointing to the download URL directly
    if len(segments) == 2 and segments[1] == "download":
        segments = segments[:1]
    if len(segments) != 1 or segments[0] in HEDGEDOC_RESERVED_PATHS:
        return None
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return urlunsplit(("https", host, f"/{segments[0]}/download", "", ""))


def get_wiki_page_title(wiki_link: str) -> tuple[dict, str] | None:
    """
    Determine the wiki and title of the page a wiki link points to

    :param wiki_link: link to the page, e.g., https://wiki.example.com/wiki/Some_Page
        or https://wiki.example.com/w/index.php?title=Some_Page
    :return: tuple of wiki configuration and page title or None if the link does not point to a page
        in one of the configured wikis
    """
    parts = urlsplit(wiki_link.strip())
    if parts.scheme not in ("http", "https"):
        return None
    wikis = {host.lower(): wiki for host, wiki in settings.PROTOCOL_MIGRATION_WIKIS.items()}
    wiki = wikis.get(parts.hostname) if parts.hostname else None
    if wiki is None:
        return None
    title = None
    article_path = wiki.get("article_path", "/wiki/")
    # Links to entry points like index.php (in the same directory as api.php) can only specify the page
    # as parameter, their path must not be mistaken for a title (e.g., with article path "/")
    script_path = urlsplit(wiki["api_url"]).path.rsplit("/", 1)[0] + "/"
    script = parts.path.removeprefix(script_path) if parts.path.startswith(script_path) else None
    is_script = script is not None and script.endswith(".php") and "/" not in script
    if "title" in (query := parse_qs(parts.query)):
        title = query["title"][0]
    elif not is_script and parts.path.startswith(article_path):
        title = unquote(parts.path[len(article_path):])
    if not title:
        return None
    return wiki, title.replace("_", " ")


def resolve_public_address(hostname: str) -> str:
    """
    Resolve a hostname to an IP address, but only if all its addresses are publicly reachable

    Protocol links are entered by users, hence downloads must not reach the server itself or internal networks

    :raises MigrationError: if the hostname cannot be resolved or resolves to a non-public address
    """
    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError) as e:
        raise MigrationError(MigrationStatus.PROTOCOL_DOWNLOAD_FAILED, f"{hostname}: {e}") from e
    addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    for address in addresses:
        # Also check IPv4 addresses embedded in IPv6 addresses (e.g., ::ffff:127.0.0.1)
        checked = getattr(address, "ipv4_mapped", None) or address
        if not checked.is_global or checked.is_multicast:
            raise MigrationError(MigrationStatus.INVALID_PROTOCOL_LINK,
                                 f"{hostname} resolves to non-public address {address}")
    return str(addresses[0])


class PinnedAddressAdapter(HTTPAdapter):
    """
    Transport adapter for connections to a fixed (previously checked) IP address
    that still uses the hostname for TLS (server name indication and certificate validation)
    """

    def __init__(self, hostname: str, **kwargs):
        # Needs to be set before calling the parent constructor since that already initializes the pool manager
        self.hostname = hostname
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["server_hostname"] = self.hostname
        kwargs["assert_hostname"] = self.hostname
        super().init_poolmanager(*args, **kwargs)


def fetch_public(url: str) -> requests.Response:
    """
    Send a GET request to an https URL (without following redirects), but only if its host is publicly reachable

    The connection is made to exactly the checked address (instead of resolving the hostname again),
    so the check cannot be circumvented by DNS answers changing in between (DNS rebinding).
    The response is streamed, i.e., the caller has to read its content and close it

    :raises MigrationError: if the host is not publicly reachable or the request fails
    """
    parts = urlsplit(url)
    if not parts.hostname:
        raise MigrationError(MigrationStatus.INVALID_PROTOCOL_LINK, url)
    address = resolve_public_address(parts.hostname)
    session = requests.Session()
    session.mount("https://", PinnedAddressAdapter(parts.hostname))
    pinned_url = urlunsplit(("https", f"[{address}]" if ":" in address else address, parts.path, parts.query, ""))
    try:
        return session.get(pinned_url, headers={"Host": parts.netloc, "User-Agent": USER_AGENT},
                           timeout=REQUEST_TIMEOUT, allow_redirects=False, stream=True)
    except requests.RequestException as e:
        raise MigrationError(MigrationStatus.PROTOCOL_DOWNLOAD_FAILED, str(e)) from e


def download_protocol(download_url: str) -> str:
    """
    Download the markdown source of a HedgeDoc note

    :raises MigrationError: if the note cannot be downloaded (e.g., because it does not exist or is not public)
        or the response does not look like the markdown source of a note
    """
    url = download_url
    for _ in range(MAX_REDIRECTS + 1):
        response = fetch_public(url)
        if response.status_code not in REDIRECT_STATUS_CODES:
            break
        response.close()
        # Only follow redirects to the download URL of a note (e.g., to another domain of the same instance).
        # HedgeDoc redirects to the login page or the note itself if the note cannot be downloaded,
        # hence, such redirects are treated as failures
        location = urljoin(url, response.headers.get("Location", ""))
        if get_hedgedoc_download_url(location) != location:
            raise MigrationError(MigrationStatus.PROTOCOL_DOWNLOAD_FAILED,
                                 f"HTTP {response.status_code}: redirected to {location}")
        url = location
    else:
        raise MigrationError(MigrationStatus.PROTOCOL_DOWNLOAD_FAILED, "Too many redirects")

    with response:
        if response.status_code != 200:
            raise MigrationError(MigrationStatus.PROTOCOL_DOWNLOAD_FAILED, f"HTTP {response.status_code}")
        # HedgeDoc serves the source of notes as markdown, anything else is not a protocol
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("text/markdown"):
            raise MigrationError(MigrationStatus.PROTOCOL_DOWNLOAD_FAILED,
                                 f"Not a HedgeDoc note (content type {content_type or 'missing'})")
        content = b""
        try:
            for chunk in response.iter_content(64 * 1024):
                content += chunk
                if len(content) > MAX_PROTOCOL_SIZE:
                    raise MigrationError(MigrationStatus.PROTOCOL_DOWNLOAD_FAILED,
                                         f"Protocol larger than {MAX_PROTOCOL_SIZE // (1024 * 1024)} MB")
        except requests.RequestException as e:
            raise MigrationError(MigrationStatus.PROTOCOL_DOWNLOAD_FAILED, str(e)) from e
    return content.decode("utf-8", errors="replace")


def convert_to_mediawiki(markdown: str) -> str:
    """
    Convert (GitHub flavored) markdown to MediaWiki syntax using pandoc

    :raises MigrationError: if pandoc is not available or the conversion fails
    """
    markdown = FRONT_MATTER.sub("", markdown, count=1)
    try:
        # Sandbox pandoc since the protocols are untrusted input (prevents access to local files and network)
        # HedgeDoc renders single line breaks as such (unlike plain GitHub flavored markdown).
        # Heading identifiers would be written as explicit anchors, but MediaWiki generates them itself
        # Enfordce LF line endings
        # (even on Windows where it would otherwise use CRLF)
        return pypandoc.convert_text(markdown, "mediawiki", format="gfm+hard_line_breaks-gfm_auto_identifiers",
                                     sandbox=True, extra_args=["--eol=lf"])
    except (OSError, RuntimeError) as e:
        raise MigrationError(MigrationStatus.CONVERSION_FAILED, str(e).strip()) from e


class MediaWikiClient:
    """
    Minimal client for the MediaWiki action API

    Authentication uses bot passwords (see Special:BotPasswords in the wiki),
    the login is performed lazily on the first request (reading may require it, too).
    Logins are stored in the cache to reuse them across requests (see :meth:`restore_session`),
    expired logins are detected and renewed automatically.
    """

    def __init__(self, wiki: dict, username: str = "", password: str = ""):
        self.api_url = wiki["api_url"]
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.csrf_token: str | None = None

    def _request(self, method: str, _retry: bool = True, **params) -> dict:
        params["format"] = "json"
        params["formatversion"] = "2"
        # Let the wiki report if the login expired (e.g., when reusing a cached login) instead of silently
        # performing the request anonymously
        if self.username and self.csrf_token is not None:
            params["assert"] = "user"
        try:
            if method == "GET":
                response = self.session.get(self.api_url, params=params, timeout=REQUEST_TIMEOUT)
            else:
                response = self.session.post(self.api_url, data=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            raise MigrationError(MigrationStatus.WIKI_ERROR, str(e)) from e
        if "error" in data:
            if _retry and data["error"].get("code") in ("assertuserfailed", "badtoken"):
                self.csrf_token = None
                self.login()
                if "token" in params:
                    params["token"] = self.csrf_token
                return self._request(method, _retry=False, **params)
            raise MigrationError(MigrationStatus.WIKI_ERROR,
                                 f"{data['error'].get('code')}: {data['error'].get('info')}")
        return data

    def _get_token(self, token_type: str) -> str:
        return self._request("GET", action="query", meta="tokens", type=token_type)["query"]["tokens"][
            f"{token_type}token"]

    def _cache_key(self) -> str:
        return f"protocol_migration_wiki_session:{self.api_url}:{self.username}"

    def restore_session(self):
        """
        Reuse the login of a previous request (if still cached) instead of logging in again
        """
        state = cache.get(self._cache_key())
        if state is not None:
            self.session.cookies.update(state["cookies"])
            self.csrf_token = state["csrf_token"]

    def login(self):
        """
        Log in (if not already done) and retrieve CSRF token needed for editing

        The resulting session is stored in the cache, see :meth:`restore_session`
        """
        if self.csrf_token is not None:
            return
        if self.username:
            result = self._request("POST", action="login", lgname=self.username, lgpassword=self.password,
                                   lgtoken=self._get_token("login"))["login"]
            if result.get("result") != "Success":
                raise MigrationError(MigrationStatus.WIKI_ERROR,
                                     f"Login failed: {result.get('reason', result.get('result'))}")
        self.csrf_token = self._get_token("csrf")
        cache.set(self._cache_key(), {"cookies": requests.utils.dict_from_cookiejar(self.session.cookies),
                                      "csrf_token": self.csrf_token}, WIKI_SESSION_CACHE_TIMEOUT)

    def get_page(self, title: str) -> tuple[bool, str, str | None, str | None]:
        """
        Retrieve the current state of a page

        :return: tuple of (page exists?, current content, timestamp of current revision,
            timestamp of this request (needed to detect deletions of the page before writing))
        :raises MigrationError: if the title is invalid or does not refer to a regular page,
            or the wiki cannot be reached or returns an unexpected response
        """
        self.login()
        data = self._request("GET", action="query", prop="revisions", rvprop="content|timestamp", rvslots="main",
                             titles=title, curtimestamp="1")
        start_timestamp = data.get("curtimestamp")
        pages = data.get("query", {}).get("pages")
        # Interwiki titles are not resolved to a page in this wiki
        if not pages:
            raise MigrationError(MigrationStatus.INVALID_WIKI_LINK, title)
        page = pages[0]
        if page.get("invalid"):
            raise MigrationError(MigrationStatus.INVALID_WIKI_LINK, page.get("invalidreason", ""))
        # Special pages (e.g., Special:RecentChanges) cannot be edited
        if page.get("special"):
            raise MigrationError(MigrationStatus.INVALID_WIKI_LINK, title)
        if page.get("missing"):
            return False, "", None, start_timestamp
        try:
            revision = page["revisions"][0]
            return True, revision["slots"]["main"].get("content", ""), revision["timestamp"], start_timestamp
        except (KeyError, IndexError, TypeError) as e:
            raise MigrationError(MigrationStatus.WIKI_ERROR, f"Unexpected API response: {page}") from e

    def write_page(self, title: str, content: str, summary: str, *, exists: bool, base_timestamp: str | None,
                   start_timestamp: str | None):
        """
        Write the given content to a page that is currently empty or missing

        Edit conflicts (i.e., someone else creating, filling or deleting the page in the meantime) are detected by
        MediaWiki and reported as errors instead of overwriting the page
        """
        self.login()
        params: dict[str, Any] = {"action": "edit", "title": title, "text": content, "summary": summary,
                                  "token": self.csrf_token}
        if start_timestamp:
            params["starttimestamp"] = start_timestamp
        if exists:
            params["nocreate"] = "1"
            params["basetimestamp"] = base_timestamp
        else:
            params["createonly"] = "1"
        result = self._request("POST", **params)["edit"]
        if result.get("result") != "Success":
            raise MigrationError(MigrationStatus.WIKI_ERROR, str(result))


def migrate_protocol(ak: AK, wiki_clients: dict[str, MediaWikiClient]) -> MigrationResult:
    """
    Migrate the protocol of a single AK from HedgeDoc to MediaWiki

    :param ak: AK to migrate the protocol for
    :param wiki_clients: cache of wiki clients (by API URL) to reuse logins across multiple AKs
    :return: result of the migration
    """
    try:
        # Check links before doing anything else
        if not ak.protocol_link:
            raise MigrationError(MigrationStatus.NO_PROTOCOL_LINK)
        download_url = get_hedgedoc_download_url(ak.protocol_link)
        if download_url is None:
            raise MigrationError(MigrationStatus.INVALID_PROTOCOL_LINK, ak.protocol_link)
        if not ak.link:
            raise MigrationError(MigrationStatus.NO_WIKI_LINK)
        wiki_page = get_wiki_page_title(ak.link)
        if wiki_page is None:
            raise MigrationError(MigrationStatus.INVALID_WIKI_LINK, ak.link)
        wiki, title = wiki_page
        if wiki["api_url"] not in wiki_clients:
            # Credentials are kept separate from the (non-secret) wiki configuration, see settings_secrets.py
            credentials = settings.PROTOCOL_MIGRATION_WIKI_CREDENTIALS.get(wiki["api_url"], {})
            client = MediaWikiClient(wiki, username=credentials.get("username", ""),
                                     password=credentials.get("password", ""))
            client.restore_session()
            wiki_clients[wiki["api_url"]] = client
        client = wiki_clients[wiki["api_url"]]

        # Do not bother downloading and converting the protocol if the page cannot be filled anyway
        exists, content, base_timestamp, start_timestamp = client.get_page(title)
        if content.strip():
            raise MigrationError(MigrationStatus.WIKI_PAGE_NOT_EMPTY, ak.link)

        markdown = download_protocol(download_url)
        if not markdown.strip():
            raise MigrationError(MigrationStatus.PROTOCOL_EMPTY, ak.protocol_link)
        wiki_text = convert_to_mediawiki(markdown)

        client.write_page(title, wiki_text, summary=f"Protocol migrated from {ak.protocol_link}",
                          exists=exists, base_timestamp=base_timestamp, start_timestamp=start_timestamp)
        return MigrationResult(ak, MigrationStatus.SUCCESS, ak.link)
    except MigrationError as e:
        return MigrationResult(ak, e.status, e.detail)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Do not abort the migration of the remaining AKs (some of which may already have been written to the wiki)
        logger.exception("Unexpected error while migrating the protocol of AK %s", ak.pk)
        return MigrationResult(ak, MigrationStatus.UNEXPECTED_ERROR, f"{type(e).__name__}: {e}")


def migrate_protocols(aks) -> list[MigrationResult]:
    """
    Migrate the protocols of the given AKs from HedgeDoc to MediaWiki

    :param aks: AKs to migrate the protocols for
    :return: list of results (one per AK)
    """
    wiki_clients: dict[str, MediaWikiClient] = {}
    return [migrate_protocol(ak, wiki_clients) for ak in aks]
