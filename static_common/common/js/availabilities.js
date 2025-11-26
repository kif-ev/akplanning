// Availability editor using fullcalendar v5

// This code was initially based on the availability editor from pretalx (https://github.com/pretalx/pretalx)
// Copyright 2017-2019, Tobias Kunze
// Original Copyrights licensed under the Apache License, Version 2.0 http://www.apache.org/licenses/LICENSE-2.0
// It was significantly changed to deal with the newer fullcalendar version, event specific timezones,
// to remove the dependency to moments timezone and improve the visualization of deletion

function createAvailabilityEditors(timezone, language, startDate, endDate, slotResolution='00:30:00') {
    $("input.availabilities-editor-data").each(function () {
        const eventColor = '#28B62C';

        let data_field = $(this);
        let editor = $('<div class="availabilities-editor">');
        editor.attr("data-name", data_field.attr("name"));
        data_field.after(editor);
        data_field.hide();

        // Add inputs to add slots without the need to click and drag
        let manualSlotAdderSource = 
            "<form id='formManualAdd'>"+
            "<div class='d-flex align-items-center justify-content-start gap-2 flex-wrap py-1 mb-0'>" +
                "<input type='datetime-local' id='inputStart' value='" + startDate + "' min='" + startDate + "' max='" + endDate + "'>" +
                "<i class='fas fa-long-arrow-alt-right'></i>" +
                "<input type='datetime-local' id='inputEnd' value='" + endDate + "' min='" + startDate + "' max='" + endDate + "'>" +
                "<button class='btn btn-primary' type='submit'><i class='fas fa-plus'></i></button>" +
            "</div>" +
            "</form>";
            let manualSlotAdder = $(manualSlotAdderSource);
        editor.after(manualSlotAdder);

        $('#formManualAdd').submit(function(event) {
            add($('#inputStart').val(), $('#inputEnd').val());
            event.preventDefault();
        });

        let editable = !Boolean(data_field.attr("disabled"));
        let data = JSON.parse(data_field.attr("value"));
        let events = data.availabilities.map(function (e) {
            start = moment(e.start);
            end = moment(e.end);
            allDay = start.format("HHmmss") === 0 && end.format("HHmmss") === 0;

            return {
                id: e.id,
                start: start.format(),
                end: end.format(),
                allDay: allDay,
                title: ""
            };
        });

        let eventMarkedForDeletion = undefined;
        let eventMarkedForDeletionEl = undefined;
        let newEventsCounter = 0;

        let plan = new FullCalendar.Calendar(editor[0], {
            timeZone: timezone,
            themeSystem: 'bootstrap5',
            buttonIcons: {
                prev: 'ignore fa-solid fa-angle-left',
                next: 'ignore fa-solid fa-angle-right',
            },
            locale: language,
            schedulerLicenseKey: 'GPL-My-Project-Is-Open-Source',
            editable: editable,
            selectable: editable,
            headerToolbar: false,
            initialView: 'timeGridWholeEvent',
            views: {
                timeGridWholeEvent: {
                    type: 'timeGrid',
                    visibleRange: {
                        start: startDate,
                        end: endDate,
                    },
                }
            },
            contentHeight: 'auto',
            allDaySlot: true,
            events: data.availabilities,
            eventBackgroundColor: eventColor,
            select: function (info) {
                add(info.start, info.end);
            },
            eventClick: function (info) {
                if (eventMarkedForDeletion !== undefined && (eventMarkedForDeletion.id === info.event.id)) {
                    info.event.remove();
                    eventMarkedForDeletion = undefined;
                    eventMarkedForDeletionEl = undefined;
                    save_events();
                } else {
                    resetDeletionCandidate();
                    makeDeletionCandidate(info.el);
                    eventMarkedForDeletion = info.event;
                    eventMarkedForDeletionEl = info.el;
                }
            },
            selectOverlap: false,
            eventOverlap: false,
            eventChange: save_events,
            slotDuration: slotResolution,
        });
        plan.render();

        function add(start, end) {
            resetDeletionCandidate();
            plan.addEvent({
                title: "",
                start: start,
                end: end,
                id: 'new' + newEventsCounter
            })
            newEventsCounter++;
            save_events();
        }

        function makeDeletionCandidate(el) {
            el.classList.add("deleteEvent");
            $(el).find(".fc-event-title").html("<i class='fas fa-trash'></i> <i class='fas fa-question'></i>");
        }

        function resetDeletionCandidate() {
            if (eventMarkedForDeletionEl !== undefined) {
                eventMarkedForDeletionEl.classList.remove("deleteEvent");
                $(eventMarkedForDeletionEl).find(".fc-event-title").html("");
            }
            eventMarkedForDeletionEl = undefined;
            eventMarkedForDeletion = undefined;
        }

        function save_events() {
            data = {
                availabilities: plan.getEvents().map(function (e) {
                    let id = e.id;
                    if(e.id.startsWith("new"))
                        id = "";
                    return {
                        id: id,
                        // Make sure these timestamps are correctly interpreted as localized ones
                        // by removing the UTC-signaler ("Z" at the end)
                        // A bit dirty, but still more elegant than creating a timestamp with the
                        // required format manually
                        start: e.start.toISOString().replace("Z", ""),
                        end: e.end.toISOString().replace("Z", ""),
                        allDay: e.allDay,
                    }
                }),
            }
            data_field.attr("value", JSON.stringify(data));
        }
    });
}
