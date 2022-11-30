// Availability editor using fullcalendar v5

// This code was initially based on the availability editor from pretalx (https://github.com/pretalx/pretalx)
// Copyright 2017-2019, Tobias Kunze
// Original Copyrights licensed under the Apache License, Version 2.0 http://www.apache.org/licenses/LICENSE-2.0
// It was significantly changed to deal with the newer fullcalendar version, event specific timezones,
// to remove the dependency to moments timezone and improve the visualization of deletion

function createAvailabilityEditors(timezone, language, startDate, endDate) {
    $("input.availabilities-editor-data").each(function () {
        const eventColor = '#28B62C';

        let data_field = $(this);
        let editor = $('<div class="availabilities-editor">');
        editor.attr("data-name", data_field.attr("name"));
        data_field.after(editor);
        data_field.hide();

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
            themeSystem: 'bootstrap',
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
            allDaySlot: true,
            events: data.availabilities,
            eventBackgroundColor: eventColor,
            select: function (info) {
                resetDeletionCandidate();
                plan.addEvent({
                    title: "",
                    start: info.start,
                    end: info.end,
                    id: 'new' + newEventsCounter
                })
                newEventsCounter++;
                save_events();
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
        });
        plan.render();

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
