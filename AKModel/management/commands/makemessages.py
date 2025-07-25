import os

from django.core.management.commands.makemessages import Command as MakeMessagesCommand


class Command(MakeMessagesCommand):
    """
    Adapted version of the :class:`MakeMessagesCommand`
    Ensure PO files are generated using forward slashes in the location comments on all operating systems
    """
    def find_files(self, root):
        # Replace backward slashes with forward slashes if necessary in file list
        all_files = super().find_files(root)
        if os.sep != "\\":
            return all_files

        for file_entry in all_files:
            if file_entry.dirpath == ".":
                file_entry.dirpath = ""
            elif file_entry.dirpath.startswith(".\\"):
                file_entry.dirpath = file_entry.dirpath[2:].replace("\\", "/")

        return all_files

    def build_potfiles(self):
        # Replace backward slashes with forward slashes if necessary in the files itself
        pot_files = super().build_potfiles()
        if os.sep != "\\":
            return pot_files

        for filename in pot_files:
            with open(filename, "r", encoding="utf-8") as f:
                lines = f.readlines()
                fixed_lines = []
                for line in lines:
                    if line.startswith("#: "):
                        line = line.replace("\\", "/")
                    fixed_lines.append(line)

            with open(filename, "w", encoding="utf-8") as f:
                f.writelines(fixed_lines)

        return pot_files
