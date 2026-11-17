// Availability editor using fullcalendar v5

// This code was initially based on the availability editor from pretalx (https://github.com/pretalx/pretalx)
// Copyright 2017-2019, Tobias Kunze
// Original Copyrights licensed under the Apache License, Version 2.0 http://www.apache.org/licenses/LICENSE-2.0
// It was significantly changed to deal with the newer fullcalendar version, event specific timezones,
// to remove the dependency to moments timezone and improve the visualization of deletion

/**
 * Editor for availabilities (or similar time ranges) based on fullcalendar.
 *
 * Replaces a (hidden) input field containing the availabilities as JSON ({availabilities: [...]})
 * with a calendar view and keeps the field updated with all changes made in the calendar.
 *
 * Subclasses can adapt the behavior by overriding the hook methods
 * renderControls, eventFromData, newEvent, serializeEvent and eventTitle.
 */
class AvailabilityEditor {
    eventColor = '#28B62C';

    constructor(dataField, timezone, language, startDate, endDate, slotResolution = '00:30:00') {
        this.dataField = $(dataField);
        this.timezone = timezone;
        this.language = language;
        this.startDate = startDate;
        this.endDate = endDate;
        this.slotResolution = slotResolution;
        this.editable = !Boolean(this.dataField.attr("disabled"));

        this.eventMarkedForDeletion = undefined;
        this.eventMarkedForDeletionEl = undefined;
        this.newEventsCounter = 0;
    }

    /**
     * Create the editor UI and render the calendar
     */
    render() {
        this.editor = $('<div class="availabilities-editor">');
        this.editor.attr("data-name", this.dataField.attr("name"));
        this.dataField.after(this.editor);
        this.dataField.hide();

        this.renderControls();
        this.renderManualSlotAdder();

        const data = JSON.parse(this.dataField.attr("value"));

        this.plan = new FullCalendar.Calendar(this.editor[0], {
            timeZone: this.timezone,
            themeSystem: 'bootstrap5',
            buttonIcons: {
                prev: 'ignore fa-solid fa-angle-left',
                next: 'ignore fa-solid fa-angle-right',
            },
            locale: this.language,
            schedulerLicenseKey: 'GPL-My-Project-Is-Open-Source',
            editable: this.editable,
            selectable: this.editable,
            headerToolbar: false,
            initialView: 'timeGridWholeEvent',
            views: {
                timeGridWholeEvent: {
                    type: 'timeGrid',
                    visibleRange: {
                        start: this.startDate,
                        end: this.endDate,
                    },
                }
            },
            contentHeight: 'auto',
            allDaySlot: true,
            events: data.availabilities.map(e => this.eventFromData(e)),
            eventBackgroundColor: this.eventColor,
            select: info => this.add(info.start, info.end),
            eventClick: info => this.handleEventClick(info),
            selectOverlap: false,
            eventOverlap: false,
            eventChange: () => this.save(),
            slotDuration: this.slotResolution,
        });
        this.plan.render();
        return this;
    }

    /**
     * Inputs to add slots without the need to click and drag
     */
    renderManualSlotAdder() {
        const manualSlotAdder = $(
            "<form id='formManualAdd'>" +
            "<div class='d-flex align-items-center justify-content-start gap-2 flex-wrap py-1 mb-0'>" +
            "<input type='datetime-local' id='inputStart' value='" + this.startDate + "' min='" + this.startDate + "' max='" + this.endDate + "'>" +
            "<i class='fas fa-long-arrow-alt-right'></i>" +
            "<input type='datetime-local' id='inputEnd' value='" + this.endDate + "' min='" + this.startDate + "' max='" + this.endDate + "'>" +
            "<button class='btn btn-primary' type='submit'><i class='fas fa-plus'></i></button>" +
            "</div>" +
            "</form>"
        );
        this.editor.after(manualSlotAdder);

        manualSlotAdder.submit(event => {
            this.add(manualSlotAdder.find('#inputStart').val(), manualSlotAdder.find('#inputEnd').val());
            event.preventDefault();
        });
    }

    add(start, end) {
        this.resetDeletionCandidate();
        this.plan.addEvent(this.newEvent(start, end, 'new' + this.newEventsCounter));
        this.newEventsCounter++;
        this.save();
    }

    // Click once to mark an event for deletion, click again to delete it
    handleEventClick(info) {
        if (this.eventMarkedForDeletion !== undefined && (this.eventMarkedForDeletion.id === info.event.id)) {
            info.event.remove();
            this.eventMarkedForDeletion = undefined;
            this.eventMarkedForDeletionEl = undefined;
            this.save();
        } else {
            this.resetDeletionCandidate();
            this.makeDeletionCandidate(info.event, info.el);
        }
    }

    makeDeletionCandidate(event, el) {
        el.classList.add("deleteEvent");
        $(el).find(".fc-event-title").html("<i class='fas fa-trash'></i> <i class='fas fa-question'></i>");
        this.eventMarkedForDeletion = event;
        this.eventMarkedForDeletionEl = el;
    }

    resetDeletionCandidate() {
        if (this.eventMarkedForDeletionEl !== undefined) {
            this.eventMarkedForDeletionEl.classList.remove("deleteEvent");
            $(this.eventMarkedForDeletionEl).find(".fc-event-title").text(this.eventTitle(this.eventMarkedForDeletion));
        }
        this.eventMarkedForDeletionEl = undefined;
        this.eventMarkedForDeletion = undefined;
    }

    /**
     * Write all events into the data field
     */
    save() {
        const data = {
            availabilities: this.plan.getEvents().map(e => this.serializeEvent(e)),
        };
        this.dataField.attr("value", JSON.stringify(data));
    }

    // --- Hooks that can be overridden by subclasses ---

    /**
     * Hook: Add additional controls to the editor (e.g., before or after this.editor)
     */
    renderControls() {
    }

    /**
     * Hook: Convert an entry of the data field into a fullcalendar event definition
     */
    eventFromData(entry) {
        return entry;
    }

    /**
     * Hook: Create the fullcalendar event definition for a newly added event
     */
    newEvent(start, end, id) {
        return {
            title: "",
            start: start,
            end: end,
            id: id,
        };
    }

    /**
     * Hook: Convert a fullcalendar event into an entry of the data field
     */
    serializeEvent(e) {
        return {
            // New events are stored without id
            id: e.id.startsWith("new") ? "" : e.id,
            // Make sure these timestamps are correctly interpreted as localized ones
            // by removing the UTC-signaler ("Z" at the end)
            // A bit dirty, but still more elegant than creating a timestamp with the
            // required format manually
            start: e.start.toISOString().replace("Z", ""),
            end: e.end.toISOString().replace("Z", ""),
            allDay: e.allDay,
        };
    }

    /**
     * Hook: Title to display for an event (used to restore the title after it was marked for deletion)
     */
    eventTitle(event) {
        return event.title;
    }
}

/**
 * Create an editor for every availability input field (input.availabilities-editor-data) on the page
 *
 * @param editorClass class to use for the editors, AvailabilityEditor or a subclass of it
 * @param editorArgs additional arguments passed to the constructor of the editor class
 */
function createAvailabilityEditors(timezone, language, startDate, endDate, slotResolution = '00:30:00',
                                   editorClass = AvailabilityEditor, ...editorArgs) {
    $("input.availabilities-editor-data").each(function () {
        new editorClass(this, timezone, language, startDate, endDate, slotResolution, ...editorArgs).render();
    });
}
