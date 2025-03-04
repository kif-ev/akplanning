import json
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta
from itertools import chain
from pathlib import Path

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry, Resource

from AKModel.availability.models import Availability
from AKModel.models import AK, AKCategory, AKOwner, AKSlot, DefaultSlot, Event, Room
from AKPlanning import settings


class JSONExportTest(TestCase):
    """Test if JSON export is correct.

    It tests if the output conforms to the KoMa specification:
    https://github.com/Die-KoMa/ak-plan-optimierung/wiki/Input-&-output-format
    """

    fixtures = ["model.json"]

    @classmethod
    def setUpTestData(cls):
        """Shared set up by initializing admin user."""
        cls.admin_user = get_user_model().objects.create(
            username="Test Admin User",
            email="testadmin@example.com",
            password="adminpw",
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

        schema_base_path = Path(settings.BASE_DIR) / "schemas"
        resources = []
        for schema_path in schema_base_path.glob("**/*.schema.json"):
            with schema_path.open("r") as ff:
                res = Resource.from_contents(json.load(ff))
            resources.append((res.id(), res))
        registry = Registry().with_resources(resources)
        with (schema_base_path / "solver-input.json").open("r") as ff:
            schema = json.load(ff)
        cls.json_export_validator = Draft202012Validator(
            schema=schema, registry=registry
        )

    def setUp(self):
        self.client.force_login(self.admin_user)
        self.export_dict = {}
        self.export_objects = {
            "aks": {},
            "rooms": {},
            "participants": {},
        }

        self.ak_slots: Iterable[AKSlot] = []
        self.rooms: Iterable[Room] = []
        self.slots_in_an_hour: float = 1.0
        self.event: Event | None = None

    def set_up_event(self, event: Event) -> None:
        """Set up by retrieving json export and initializing data."""

        export_url = reverse("admin:ak_json_export", kwargs={"event_slug": event.slug})
        response = self.client.get(export_url)

        self.assertEqual(response.status_code, 200, "Export not working at all")

        soup = BeautifulSoup(response.content, features="lxml")
        self.export_dict = json.loads(soup.find("pre").string)

        self.export_objects["aks"] = {ak["id"]: ak for ak in self.export_dict["aks"]}
        self.export_objects["rooms"] = {
            room["id"]: room for room in self.export_dict["rooms"]
        }
        self.export_objects["participants"] = {
            participant["id"]: participant
            for participant in self.export_dict["participants"]
        }

        self.ak_slots = (
            AKSlot.objects.filter(event__slug=event.slug)
            .select_related("ak")
            .prefetch_related("ak__conflicts")
            .prefetch_related("ak__prerequisites")
            .all()
        )
        self.rooms = Room.objects.filter(event__slug=event.slug).all()
        self.slots_in_an_hour = 1 / self.export_dict["timeslots"]["info"]["duration"]
        self.event = event

    def test_all_aks_exported(self):
        """Test if exported AKs match AKSlots of Event."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)
                self.assertEqual(
                    {slot.pk for slot in self.ak_slots},
                    self.export_objects["aks"].keys(),
                    "Exported AKs does not match the AKSlots of the event",
                )

    def _check_uniqueness(self, lst, name: str, key: str | None = "id"):
        if key is not None:
            lst = [entry[key] for entry in lst]
        self.assertEqual(len(lst), len(set(lst)), f"{name} IDs not unique!")

    def _check_type(self, attr, cls, name: str, item: str) -> None:
        self.assertTrue(isinstance(attr, cls), f"{item} {name} not a {cls}")

    def _check_lst(
        self, lst: list[str], name: str, item: str, contained_type=str
    ) -> None:
        self.assertTrue(isinstance(lst, list), f"{item} {name} not a list")
        self.assertTrue(
            all(isinstance(c, contained_type) for c in lst),
            f"{item} has non-{contained_type} {name}",
        )
        if contained_type in {str, int}:
            self._check_uniqueness(lst, name, key=None)

    def test_conformity_to_schema(self):
        """Test if JSON structure and types conform to schema."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                errors = list(self.json_export_validator.iter_errors(self.export_dict))
                msg = "" if not errors else best_match(errors).message
                self.assertFalse(errors, msg)

    def test_id_uniqueness(self):
        """Test if objects are only exported once."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                self._check_uniqueness(self.export_dict["aks"], "AKs")
                self._check_uniqueness(self.export_dict["rooms"], "Rooms")
                self._check_uniqueness(self.export_dict["participants"], "Participants")

                self._check_uniqueness(
                    chain.from_iterable(self.export_dict["timeslots"]["blocks"]),
                    "Timeslots",
                )

    def test_timeslot_ids_consecutive(self):
        """Test if Timeslots ids are chronologically consecutive."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                prev_id = None
                for timeslot in chain.from_iterable(
                    self.export_dict["timeslots"]["blocks"]
                ):
                    if prev_id is not None:
                        self.assertLess(
                            prev_id,
                            timeslot["id"],
                            "timeslot ids must be increasing",
                        )
                    prev_id = timeslot["id"]

    def test_general_conformity_to_spec(self):
        """Test if rest of JSON structure and types conform to standard."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                self.assertEqual(
                    self.export_dict["participants"],
                    [],
                    "Empty participant list expected",
                )

                info_keys = {"title": "name", "slug": "slug"}
                for attr in ["contact_email", "place"]:
                    if hasattr(self.event, attr) and getattr(self.event, attr):
                        info_keys[attr] = attr
                self.assertEqual(
                    self.export_dict["info"].keys(),
                    info_keys.keys(),
                    "info keys not as expected",
                )
                for attr, attr_field in info_keys.items():
                    self.assertEqual(
                        getattr(self.event, attr_field), self.export_dict["info"][attr]
                    )

    def test_ak_durations(self):
        """Test if all AK durations are correct."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for slot in self.ak_slots:
                    ak = self.export_objects["aks"][slot.pk]

                    self.assertLessEqual(
                        float(slot.duration) * self.slots_in_an_hour - 1e-4,
                        ak["duration"],
                        "Slot duration is too short",
                    )

                    self.assertEqual(
                        math.ceil(float(slot.duration) * self.slots_in_an_hour - 1e-4),
                        ak["duration"],
                        "Slot duration is wrong",
                    )

                    self.assertEqual(
                        float(slot.duration),
                        ak["info"]["duration_in_hours"],
                        "Slot duration_in_hours is wrong",
                    )

    def test_ak_conflicts(self):
        """Test if all AK conflicts are correct."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for slot in self.ak_slots:
                    ak = self.export_objects["aks"][slot.pk]
                    conflict_slots = set(
                        self.ak_slots.filter(
                            ak__in=slot.ak.conflicts.all()
                        ).values_list("pk", flat=True)
                    )

                    other_ak_slots = (
                        self.ak_slots.filter(ak=slot.ak)
                        .exclude(pk=slot.pk)
                        .values_list("pk", flat=True)
                    )
                    conflict_slots.update(other_ak_slots)

                    self.assertEqual(
                        conflict_slots,
                        set(ak["properties"]["conflicts"]),
                        f"Conflicts for slot {slot.pk} not as expected",
                    )

    def test_ak_depenedencies(self):
        """Test if all AK dependencies are correct."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for slot in self.ak_slots:
                    ak = self.export_objects["aks"][slot.pk]
                    dependency_slots = self.ak_slots.filter(
                        ak__in=slot.ak.prerequisites.all()
                    ).values_list("pk", flat=True)

                    self.assertEqual(
                        set(dependency_slots),
                        set(ak["properties"]["dependencies"]),
                        f"Dependencies for slot {slot.pk} not as expected",
                    )

    def test_ak_reso(self):
        """Test if resolution intent of AKs is correctly exported."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for slot in self.ak_slots:
                    ak = self.export_objects["aks"][slot.pk]
                    self.assertEqual(slot.ak.reso, ak["info"]["reso"])
                    self.assertEqual(
                        slot.ak.reso, "resolution" in ak["time_constraints"]
                    )

    def test_ak_info(self):
        """Test if contents of AK info dict is correct."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for slot in self.ak_slots:
                    ak = self.export_objects["aks"][slot.pk]
                    self.assertEqual(ak["info"]["name"], slot.ak.name)
                    self.assertEqual(
                        ak["info"]["head"], ", ".join(map(str, slot.ak.owners.all()))
                    )
                    self.assertEqual(ak["info"]["description"], slot.ak.description)
                    self.assertEqual(ak["info"]["django_ak_id"], slot.ak.pk)
                    self.assertEqual(
                        ak["info"]["types"],
                        list(slot.ak.types.values_list("name", flat=True).order_by()),
                    )

    def test_ak_room_constraints(self):
        """Test if AK room constraints are exported as expected."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for slot in self.ak_slots:
                    ak = self.export_objects["aks"][slot.pk]
                    requirements = list(
                        slot.ak.requirements.values_list("name", flat=True)
                    )

                    # proxy rooms
                    if not any(constr.startswith("proxy") for constr in requirements):
                        requirements.append("no-proxy")

                    # fixed slot
                    if slot.fixed and slot.room is not None:
                        requirements.append(f"fixed-room-{slot.room.pk}")

                    self.assertEqual(
                        set(ak["room_constraints"]),
                        set(requirements),
                        f"Room constraints for slot {slot.pk} not as expected",
                    )

    def test_ak_time_constraints(self):
        """Test if AK time constraints are exported as expected."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for slot in self.ak_slots:
                    time_constraints = set()

                    # add time constraints for AK category
                    if slot.ak.category:
                        category_constraints = AKCategory.create_category_constraints(
                            [slot.ak.category]
                        )
                        time_constraints |= category_constraints

                    if slot.fixed and slot.start is not None:
                        # fixed slot
                        time_constraints.add(f"fixed-akslot-{slot.pk}")
                    elif not Availability.is_event_covered(
                        slot.event, slot.ak.availabilities.all()
                    ):
                        # restricted AK availability
                        time_constraints.add(f"availability-ak-{slot.ak.pk}")

                    for owner in slot.ak.owners.all():
                        # restricted owner availability
                        if not owner.availabilities.all():
                            # no availability for owner -> assume full event is covered
                            continue

                        if not Availability.is_event_covered(
                            slot.event, owner.availabilities.all()
                        ):
                            time_constraints.add(f"availability-person-{owner.pk}")

                    ak = self.export_objects["aks"][slot.pk]
                    self.assertEqual(
                        set(ak["time_constraints"]),
                        time_constraints,
                        f"Time constraints for slot {slot.pk} not as expected",
                    )

    def test_all_rooms_exported(self):
        """Test if exported Rooms match the rooms of Event."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                self.assertEqual(
                    {room.pk for room in self.rooms},
                    self.export_objects["rooms"].keys(),
                    "Exported Rooms do not match the Rooms of the event",
                )

    def test_room_capacity(self):
        """Test if room capacity is exported correctly."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for room in self.rooms:
                    export_room = self.export_objects["rooms"][room.pk]
                    self.assertEqual(room.capacity, export_room["capacity"])

    def test_room_info(self):
        """Test if contents of Room info dict is correct."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for room in self.rooms:
                    export_room = self.export_objects["rooms"][room.pk]
                    self.assertEqual(room.name, export_room["info"]["name"])

    def test_room_timeconstraints(self):
        """Test if Room time constraints are exported as expected."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for room in self.rooms:
                    time_constraints = set()

                    # test if time availability of room is restricted
                    if not Availability.is_event_covered(
                        event, room.availabilities.all()
                    ):
                        time_constraints.add(f"availability-room-{room.pk}")

                    export_room = self.export_objects["rooms"][room.pk]
                    self.assertEqual(
                        time_constraints, set(export_room["time_constraints"])
                    )

    def test_room_fulfilledroomconstraints(self):
        """Test if room constraints fulfilled by Room are correct."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                for room in self.rooms:
                    # room properties
                    fulfilled_room_constraints = set(
                        room.properties.values_list("name", flat=True)
                    )

                    # proxy rooms
                    if not any(
                        constr.startswith("proxy")
                        for constr in fulfilled_room_constraints
                    ):
                        fulfilled_room_constraints.add("no-proxy")

                    fulfilled_room_constraints.add(f"fixed-room-{room.pk}")

                    export_room = self.export_objects["rooms"][room.pk]
                    self.assertEqual(
                        fulfilled_room_constraints,
                        set(export_room["fulfilled_room_constraints"]),
                    )

    def _get_timeslot_start_end(self, timeslot):
        start = datetime.strptime(timeslot["info"]["start"], "%Y-%m-%d %H:%M").replace(
            tzinfo=self.event.timezone
        )
        end = datetime.strptime(timeslot["info"]["end"], "%Y-%m-%d %H:%M").replace(
            tzinfo=self.event.timezone
        )
        return start, end

    def _get_cat_availability_in_export(self):
        export_slot_cat_avails = defaultdict(list)
        for timeslot in chain.from_iterable(self.export_dict["timeslots"]["blocks"]):
            for constr in timeslot["fulfilled_time_constraints"]:
                if constr.startswith("availability-cat-"):
                    cat_name = constr[len("availability-cat-") :]
                    start, end = self._get_timeslot_start_end(timeslot)
                    export_slot_cat_avails[cat_name].append(
                        Availability(event=self.event, start=start, end=end)
                    )
        return {
            cat_name: Availability.union(avail_lst)
            for cat_name, avail_lst in export_slot_cat_avails.items()
        }

    def _get_cat_availability(self):
        if DefaultSlot.objects.filter(event=self.event).exists():
            # Event has default slots -> use them for category availability
            default_slots_avails = defaultdict(list)
            for def_slot in DefaultSlot.objects.filter(event=self.event).all():
                avail = Availability(
                    event=self.event,
                    start=def_slot.start.astimezone(self.event.timezone),
                    end=def_slot.end.astimezone(self.event.timezone),
                )
                for cat in def_slot.primary_categories.all():
                    default_slots_avails[cat.name].append(avail)

            return {
                cat_name: Availability.union(avail_lst)
                for cat_name, avail_lst in default_slots_avails.items()
            }

        # Event has no default slots -> all categories available through whole event
        start = self.event.start.astimezone(self.event.timezone)
        end = self.event.end.astimezone(self.event.timezone)
        delta = (end - start).total_seconds()

        # tweak event end
        # 1. shorten event to match discrete slot grid
        slot_seconds = 3600 / self.slots_in_an_hour
        remainder_seconds = delta % slot_seconds
        remainder_seconds += 1  # add a second to compensate rounding errs
        end -= timedelta(seconds=remainder_seconds)

        # set seconds and microseconds to 0 as they are not exported to the json
        start -= timedelta(seconds=start.second, microseconds=start.microsecond)
        end -= timedelta(seconds=end.second, microseconds=end.microsecond)
        event_avail = Availability(event=self.event, start=start, end=end)

        category_names = AKCategory.objects.filter(event=self.event).values_list(
            "name", flat=True
        )
        return {cat_name: [event_avail] for cat_name in category_names}

    def test_timeslots_consecutive(self):
        """Test if consecutive timeslots in JSON are in fact consecutive."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                prev_end = None
                for timeslot in chain.from_iterable(
                    self.export_dict["timeslots"]["blocks"]
                ):
                    start, end = self._get_timeslot_start_end(timeslot)
                    self.assertLess(start, end)

                    delta = end - start
                    self.assertAlmostEqual(
                        delta.total_seconds() / (3600), 1 / self.slots_in_an_hour
                    )

                    if prev_end is not None:
                        self.assertLessEqual(prev_end, start)
                    prev_end = end

    def test_block_cover_categories(self):
        """Test if blocks covers all default slot resp. whole event per category."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)
                category_names = AKCategory.objects.filter(event=event).values_list(
                    "name", flat=True
                )

                export_cat_avails = self._get_cat_availability_in_export()
                cat_avails = self._get_cat_availability()

                for cat_name in category_names:
                    for avail in cat_avails[cat_name]:
                        # check that all category availabilities are covered
                        self.assertTrue(
                            avail.is_covered(export_cat_avails[cat_name]),
                            f"AKCategory {cat_name}: avail ({avail.start} – {avail.end}) "
                            f"not covered by {[f'({a.start} – {a.end})' for a in export_cat_avails[cat_name]]}",
                        )

    def _is_restricted_and_contained_slot(
        self, slot: Availability, availabilities: list[Availability]
    ) -> bool:
        """Test if object is not available for whole event and may happen during slot."""
        return slot.is_covered(availabilities) and not Availability.is_event_covered(
            self.event, availabilities
        )

    def _is_ak_fixed_in_slot(
        self,
        ak_slot: AKSlot,
        timeslot_avail: Availability,
    ) -> bool:
        if not ak_slot.fixed or ak_slot.start is None:
            return False
        ak_slot_avail = Availability(
            event=self.event,
            start=ak_slot.start.astimezone(self.event.timezone),
            end=ak_slot.end.astimezone(self.event.timezone),
        )
        return timeslot_avail.overlaps(ak_slot_avail, strict=True)

    def test_timeslot_fulfilledconstraints(self):
        """Test if fulfilled time constraints by timeslot are as expected."""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                cat_avails = self._get_cat_availability()
                num_blocks = len(self.export_dict["timeslots"]["blocks"])
                for block_idx, block in enumerate(
                    self.export_dict["timeslots"]["blocks"]
                ):
                    for timeslot in block:
                        start, end = self._get_timeslot_start_end(timeslot)
                        timeslot_avail = Availability(
                            event=self.event, start=start, end=end
                        )

                        fulfilled_time_constraints = set()

                        # reso deadline
                        if self.event.reso_deadline is not None:
                            # timeslot ends before deadline
                            if end < self.event.reso_deadline.astimezone(
                                self.event.timezone
                            ):
                                fulfilled_time_constraints.add("resolution")

                        # add category constraints
                        fulfilled_time_constraints |= (
                            AKCategory.create_category_constraints(
                                [
                                    cat
                                    for cat in AKCategory.objects.filter(
                                        event=self.event
                                    ).all()
                                    if timeslot_avail.is_covered(cat_avails[cat.name])
                                ]
                            )
                        )

                        # add owner constraints
                        fulfilled_time_constraints |= {
                            f"availability-person-{owner.id}"
                            for owner in AKOwner.objects.filter(event=self.event).all()
                            if self._is_restricted_and_contained_slot(
                                timeslot_avail,
                                Availability.union(owner.availabilities.all()),
                            )
                        }

                        # add room constraints
                        fulfilled_time_constraints |= {
                            f"availability-room-{room.id}"
                            for room in self.rooms
                            if self._is_restricted_and_contained_slot(
                                timeslot_avail,
                                Availability.union(room.availabilities.all()),
                            )
                        }

                        # add ak constraints
                        fulfilled_time_constraints |= {
                            f"availability-ak-{ak.id}"
                            for ak in AK.objects.filter(event=event)
                            if self._is_restricted_and_contained_slot(
                                timeslot_avail,
                                Availability.union(ak.availabilities.all()),
                            )
                        }
                        fulfilled_time_constraints |= {
                            f"fixed-akslot-{slot.id}"
                            for slot in self.ak_slots
                            if self._is_ak_fixed_in_slot(slot, timeslot_avail)
                        }

                        fulfilled_time_constraints |= {
                            f"notblock{idx}"
                            for idx in range(num_blocks)
                            if idx != block_idx
                        }

                        self.assertEqual(
                            fulfilled_time_constraints,
                            set(timeslot["fulfilled_time_constraints"]),
                        )

    def test_timeslots_info(self):
        """Test timeslots info dict"""
        for event in Event.objects.all():
            with self.subTest(event=event):
                self.set_up_event(event=event)

                self.assertAlmostEqual(
                    self.export_dict["timeslots"]["info"]["duration"],
                    float(self.event.export_slot),
                )

                block_names = []
                for block in self.export_dict["timeslots"]["blocks"]:
                    if not block:
                        continue

                    block_start, _ = self._get_timeslot_start_end(block[0])
                    _, block_end = self._get_timeslot_start_end(block[-1])

                    start_day = block_start.strftime("%A, %d. %b")
                    if block_start.date() == block_end.date():
                        # same day
                        time_str = (
                            block_start.strftime("%H:%M")
                            + " – "
                            + block_end.strftime("%H:%M")
                        )
                    else:
                        # different days
                        time_str = (
                            block_start.strftime("%a %H:%M")
                            + " – "
                            + block_end.strftime("%a %H:%M")
                        )
                    block_names.append([start_day, time_str])
                self.assertEqual(
                    block_names, self.export_dict["timeslots"]["info"]["blocknames"]
                )
