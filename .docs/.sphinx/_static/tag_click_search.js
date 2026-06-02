// Lock DataTable column widths after initialization to prevent
// the browser from redistributing space when search filters rows.
// With table-layout: auto, the browser recalculates column widths
// based on visible content, causing subtle column shifts.
$(document).ready(function () {
    $("table.sphinx-datatable").each(function () {
        $(this).find("thead th").each(function () {
            var w = $(this).outerWidth();
            $(this).css({"min-width": w + "px", "max-width": w + "px"});
        });
    });
});

// Click a tag (e.g. #security) to search the DataTable for that tag.
$(document).ready(function () {
    $(document).on("click", ".tag-div", function (e) {
        e.preventDefault();
        var tag = $(this).clone().children().remove().end().text().trim();
        var table = $(this).closest("table.dataTable");
        if (table.length) {
            var dt = table.DataTable();
            dt.search(tag).draw();
            // Also update the visible search input
            var wrapper = $(table).closest(".dataTables_wrapper");
            wrapper.find("input[type='search']").val(tag);
        }
    });
});
