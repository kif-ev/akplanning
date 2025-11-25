"""
This script is used to create a json export of all entries of a specific event.
I should be run after the django dumpdata command has been executed, please use json_export.sh to do so.

first parameter/argument: event id as integer
second parameter/argument: target name for the export file (without .json)
"""

import json
import sys

if __name__ == "__main__":

    event_id = int(sys.argv[1])
    target_name = sys.argv[2]

    print(f"Creating export for event '{event_id}' as '{target_name}'")

    # Load json file just created by django
    with open('backups/akplanning_only.json', 'r') as json_file:
        exported_entries = json.load(json_file)

    print(f"Loaded {len(exported_entries)} entries in total, restricting to event...")

    entries_without_event = 0
    entries_out = []
    virtual_rooms_to_preserve = set()

    # Loop over all dumped entries
    for entry in exported_entries:
        # Remove info about users that changed AKs in backend to avoid problems on import
        if entry['model'] == "AKModel.historicalak":
            entry['fields']['history_user'] = None
        # Handle all entries with event reference
        if "event" in entry['fields']:
            event = int(entry['fields']['event'])

            # Does this entry belong to the event we are looking for?
            if event == event_id:
                # Store for backup
                entries_out.append(entry)

                # Remember the primary keys of all rooms of this event
                # Required for special handling of virtual rooms,
                # since they inherit from normal rooms and have no direct event reference
                if entry['model'] == "AKModel.room":
                    virtual_rooms_to_preserve.add(entry['pk'])

        # Handle entries without event reference
        else:
            # Backup virtual rooms of that event
            if entry['model'] == "AKOnline.virtualroom":
                if entry['pk'] in virtual_rooms_to_preserve:
                    entries_out.append(entry)
            # Backup the event itself
            elif entry['model'] == "AKModel.event":
                if int(entry['pk']) == event_id:
                    entries_out.append(entry)
            else:
                # This should normally not happen (all other models should have a reference to the event)
                entries_without_event += 1
                print(entry)

    print(f"Ignored entries without event: {entries_without_event}")
    print(f"Exporting {len(entries_out)} entries for event")

    with open(f'backups/{target_name}.json', 'w') as json_file:
        json.dump(entries_out, json_file, indent=2)
