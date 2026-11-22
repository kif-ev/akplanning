from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from AKModel.models import Event, Room
from AKModel.room_import import decode_csv_bytes, detect_delimiter, import_rooms, parse_rooms_csv
from AKOnline.models import VirtualRoom


class RoomImportParsingTests(TestCase):
    """
    Test parsing and validation of CSV room data (without the views)
    """
    fixtures = ["model.json"]

    def setUp(self):
        """
        Load the event used for testing
        """
        self.event = Event.objects.get(slug="kif42")

    def _error_lines(self, result):
        """
        Get the set of lines containing errors
        """
        return {line for line, _error in result.errors}

    def test_valid_data(self):
        """
        Test that valid data is parsed correctly including defaults and requirements
        """
        result = parse_rooms_csv("name;location;capacity;url;BBB;Mumble\n"
                                 "HS 1;S101;100;https://example.com/hs1;x;\n"
                                 "HS 2;S101;;;;X\n", self.event)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        self.assertEqual(len(result.rooms), 2)
        self.assertEqual(result.rooms[0].capacity, 100)
        self.assertEqual([r.name for r in result.rooms[0].requirements], ["BBB"])
        self.assertEqual(result.rooms[1].capacity, -1)
        self.assertEqual([r.name for r in result.rooms[1].requirements], ["Mumble"])

    def test_missing_name_column(self):
        """
        Test that data without a name column is rejected
        """
        with self.assertRaises(ValidationError):
            parse_rooms_csv("location;capacity\nS101;10\n", self.event)

    def test_empty_data(self):
        """
        Test that empty data is rejected
        """
        with self.assertRaises(ValidationError):
            parse_rooms_csv("  \n", self.event)

    def test_duplicate_column(self):
        """
        Test that data with duplicate columns is rejected
        """
        with self.assertRaises(ValidationError):
            parse_rooms_csv("name;Name\nA;B\n", self.event)

    def test_invalid_capacity(self):
        """
        Test that non-numeric or negative capacities are reported, surrounding whitespace is ignored
        """
        result = parse_rooms_csv("name;capacity\nA;ca. 30\nB;-5\nC; 12 \n", self.event)
        self.assertEqual(self._error_lines(result), {2, 3})
        self.assertEqual([(r.name, r.capacity) for r in result.rooms], [("C", 12)])

    def test_short_and_long_rows(self):
        """
        Test that missing cells are treated as empty and additional cells produce a warning
        """
        result = parse_rooms_csv("name;location;capacity;url;BBB\nA\nB;L;5;;x;surplus\n", self.event)
        self.assertEqual(result.errors, [])
        self.assertEqual([(r.name, r.location, r.capacity, r.url) for r in result.rooms],
                         [("A", "", -1, ""), ("B", "L", 5, "")])
        self.assertEqual(len(result.warnings), 1)

    def test_whitespace_and_header_case(self):
        """
        Test that whitespace is stripped and column names are matched case-insensitively
        """
        result = parse_rooms_csv(" Name ; LOCATION ; bbb \n  HS 1  ; S101 ; x \n", self.event)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        room = result.rooms[0]
        self.assertEqual((room.name, room.location), ("HS 1", "S101"))
        self.assertEqual([r.name for r in room.requirements], ["BBB"])

    def test_empty_rows_skipped(self):
        """
        Test that empty rows are skipped
        """
        result = parse_rooms_csv("name;location;BBB\nA;;\n;;\n\n;;;\nB;;\n", self.event)
        self.assertEqual(result.errors, [])
        self.assertEqual([r.name for r in result.rooms], ["A", "B"])

    def test_empty_name(self):
        """
        Test that rows without a name are reported
        """
        result = parse_rooms_csv("name;location\n;S101\n", self.event)
        self.assertEqual(self._error_lines(result), {2})
        self.assertEqual(result.rooms, [])

    def test_unknown_column_warning(self):
        """
        Test that unknown columns produce a warning, empty column names are ignored
        """
        result = parse_rooms_csv("name;Beamr;;\nA;x;;\n", self.event)
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Beamr", result.warnings[0])
        self.assertEqual(len(result.rooms), 1)

    def test_requirement_markers(self):
        """
        Test that different markers for requirements are understood and unknown values reported
        """
        result = parse_rooms_csv("name;BBB\nA;ja\nB;✓\nC;nein\nD;vielleicht\n", self.event)
        self.assertEqual({r.name: [q.name for q in r.requirements] for r in result.rooms},
                         {"A": ["BBB"], "B": ["BBB"], "C": []})
        self.assertEqual(self._error_lines(result), {5})

    def test_duplicates(self):
        """
        Test that rooms already existing or appearing twice in the data are reported
        """
        # "Testraum" in "BBB" already exists in the fixture, the other duplicate is within the data
        result = parse_rooms_csv("name;location\nTestraum;BBB\nNeu;X\nneu;x\nTestraum;Anderswo\n", self.event)
        self.assertEqual(self._error_lines(result), {2, 4})
        self.assertEqual([r.name for r in result.rooms], ["Neu", "Testraum"])

    def test_field_lengths_and_url(self):
        """
        Test that too long names and invalid URLs are reported
        """
        result = parse_rooms_csv(f"name;url\n{'a' * 65};\nB;no url\nC;https://example.com\n", self.event)
        self.assertEqual(self._error_lines(result), {2, 3})
        self.assertEqual([r.name for r in result.rooms], ["C"])

    def test_quoted_and_multiline_cells(self):
        """
        Test that quoted cells (containing delimiters or line breaks) are supported
        """
        result = parse_rooms_csv('"name";"location"\n"A; B";"Line 1\nLine 2"\nC;\n', self.event)
        self.assertEqual(result.errors, [])
        self.assertEqual([r.name for r in result.rooms], ["A; B", "C"])
        # Line numbers refer to the end of a (multiline) row
        self.assertEqual([r.line for r in result.rooms], [3, 4])

    def test_delimiter_detection(self):
        """
        Test that the delimiter is detected correctly
        """
        self.assertEqual(detect_delimiter("name;location"), ";")
        self.assertEqual(detect_delimiter("name,location"), ",")
        self.assertEqual(detect_delimiter("name\tlocation"), "\t")
        self.assertEqual(detect_delimiter('name;"Kein Raum, nur Treffpunkt"'), ";")
        self.assertEqual(detect_delimiter('name,"a;b"'), ",")
        self.assertEqual(detect_delimiter("name"), ";")
        result = parse_rooms_csv("name,location,capacity\nA,L,10\n", self.event)
        self.assertEqual([(r.name, r.location, r.capacity) for r in result.rooms], [("A", "L", 10)])

    def test_decoding(self):
        """
        Test decoding of UTF-8 (with and without byte order mark) and Windows-1252
        """
        self.assertEqual(decode_csv_bytes("name\nHörsaal".encode("utf-8")), "name\nHörsaal")
        self.assertEqual(decode_csv_bytes("name\nHörsaal".encode("utf-8-sig")), "name\nHörsaal")
        self.assertEqual(decode_csv_bytes("name\nHörsaal".encode("cp1252")), "name\nHörsaal")
        # Byte order mark in text input
        result = parse_rooms_csv("﻿name\nA\n", self.event)
        self.assertEqual(len(result.rooms), 1)

    def test_import(self):
        """
        Test that rooms are created including virtual rooms, requirements and default availabilities
        """
        result = parse_rooms_csv("name;location;capacity;url;BBB;Matrix\n"
                                 "HS 1;S101;100;https://example.com/hs1;x;x\n"
                                 "HS 2;S101;;;;\n", self.event)
        self.assertEqual(import_rooms(result, self.event, create_default_availabilities=True), 2)
        hs1 = Room.objects.get(event=self.event, name="HS 1")
        self.assertEqual(hs1.capacity, 100)
        self.assertEqual(sorted(hs1.properties.values_list("name", flat=True)), ["BBB", "Matrix"])
        self.assertEqual(hs1.virtual.url, "https://example.com/hs1")
        self.assertEqual(hs1.availabilities.count(), 1)
        hs2 = Room.objects.get(event=self.event, name="HS 2")
        self.assertEqual(hs2.capacity, -1)
        self.assertFalse(VirtualRoom.objects.filter(room=hs2).exists())


class RoomImportViewTests(TestCase):
    """
    Test the two-step import process (preview and confirmation)
    """
    fixtures = ["model.json"]

    def setUp(self):
        """
        Load the event used for testing
        """
        self.event = Event.objects.get(slug="kif42")
        self.admin_user = get_user_model().objects.create(username="Test Admin User", is_staff=True,
                                                          is_superuser=True, is_active=True)
        self.client.force_login(self.admin_user)
        self.import_url = reverse("admin:room-import", kwargs={"event_slug": "kif42"})
        self.confirm_url = reverse("admin:room-import-confirm", kwargs={"event_slug": "kif42"})

    def test_preview_does_not_import(self):
        """
        Test that the first step only shows a preview and does not create rooms
        """
        room_count = Room.objects.count()
        response = self.client.post(self.import_url, {"csv_data": "name;capacity\nNeu;10\nKaputt;viele\n"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/AKModel/import_rooms_preview.html")
        self.assertEqual(len(response.context["result"].rooms), 1)
        self.assertEqual(len(response.context["result"].errors), 1)
        self.assertEqual(Room.objects.count(), room_count)

    def test_preview_of_uploaded_file(self):
        """
        Test that uploaded files are decoded and their data is used for the next steps
        """
        csv_file = SimpleUploadedFile("rooms.csv", "name;location\nHörsaal;S101\n".encode("cp1252"))
        response = self.client.post(self.import_url, {"csv_file": csv_file})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["result"].rooms[0].name, "Hörsaal")
        # Data is made available for corrections and the confirmation
        self.assertEqual(response.context["confirm_form"].initial["csv_data"], "name;location\nHörsaal;S101\n")
        self.assertEqual(response.context["form"].initial["csv_data"], "name;location\nHörsaal;S101\n")

    def test_preview_invalid_structure(self):
        """
        Test that data that cannot be imported at all is reported in the first step
        """
        response = self.client.post(self.import_url, {"csv_data": "location\nS101\n"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/AKModel/import_rooms.html")
        self.assertIn("CSV must contain a name column", response.context["form"].non_field_errors())

    def test_confirm_imports_valid_rows(self):
        """
        Test that the confirmation imports all valid rows and skips the others
        """
        response = self.client.post(self.confirm_url, {"csv_data": "name;capacity\nNeu;10\nKaputt;viele\n",
                                                       "create_default_availabilities": "True"})
        self.assertRedirects(response, reverse("admin:event_status", kwargs={"event_slug": "kif42"}))
        self.assertTrue(Room.objects.filter(event=self.event, name="Neu", capacity=10).exists())
        self.assertFalse(Room.objects.filter(event=self.event, name="Kaputt").exists())
        self.assertEqual(Room.objects.get(event=self.event, name="Neu").availabilities.count(), 1)
        self.assertEqual([m.message for m in get_messages(response.wsgi_request)],
                         ["Skipped 1 line(s) with errors", "Imported 1 room(s)"])

    def test_confirm_revalidates(self):
        """
        Test that the data is validated again when confirming
        """
        # Room was created between preview and confirmation and must not be imported twice
        Room.objects.create(event=self.event, name="Neu", location="", capacity=-1)
        response = self.client.post(self.confirm_url, {"csv_data": "name\nNeu\n"})
        self.assertRedirects(response, reverse("admin:event_status", kwargs={"event_slug": "kif42"}))
        self.assertEqual(Room.objects.filter(event=self.event, name="Neu").count(), 1)

    def test_confirm_get_redirects(self):
        """
        Test that the confirmation view redirects to the first step when accessed directly
        """
        response = self.client.get(self.confirm_url)
        self.assertRedirects(response, self.import_url)

    def test_confirm_staff_only(self):
        """
        Test that the confirmation view cannot be used without login
        """
        self.client.logout()
        response = self.client.post(self.confirm_url, {"csv_data": "name\nNeu\n"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Room.objects.filter(event=self.event, name="Neu").exists())
