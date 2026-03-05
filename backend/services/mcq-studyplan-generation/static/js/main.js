// Main JavaScript file

$(document).ready(function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        $('.alert').fadeOut('slow');
    }, 5000);

    // File upload preview
    $('input[type="file"]').on('change', function() {
        var files = $(this)[0].files;
        var fileList = '';
        for (var i = 0; i < files.length; i++) {
            fileList += '<span class="badge bg-info me-1">' + files[i].name + '</span>';
        }
        $(this).after('<div class="mt-2">' + fileList + '</div>');
    });

    // Refresh data button
    $('#refreshData').on('click', function() {
        var btn = $(this);
        btn.html('<span class="spinner-border spinner-border-sm" role="status"></span> Refreshing...');
        btn.prop('disabled', true);

        $.post('/process', function(data) {
            if (data.success) {
                location.reload();
            } else {
                alert('Error refreshing data: ' + data.message);
                btn.html('<i class="fas fa-sync-alt me-2"></i>Refresh Data');
                btn.prop('disabled', false);
            }
        }).fail(function() {
            alert('Error connecting to server');
            btn.html('<i class="fas fa-sync-alt me-2"></i>Refresh Data');
            btn.prop('disabled', false);
        });
    });

    // Study plan form validation
    $('#studyPlanForm').on('submit', function(e) {
        var examDate = new Date($('input[name="exam_date"]').val());
        var today = new Date();
        today.setHours(0, 0, 0, 0);

        if (examDate < today) {
            e.preventDefault();
            alert('Exam date must be in the future');
        }
    });

    // Export table to CSV
    $('#exportTable').on('click', function() {
        var table = $(this).data('table');
        var csv = [];
        var rows = $(table + ' tr');

        for (var i = 0; i < rows.length; i++) {
            var row = [], cols = rows[i].querySelectorAll('td, th');
            for (var j = 0; j < cols.length; j++) {
                row.push(cols[j].innerText);
            }
            csv.push(row.join(','));
        }

        // Download CSV file
        var csvFile = new Blob([csv.join('\n')], {type: 'text/csv'});
        var downloadLink = document.createElement('a');
        downloadLink.download = 'export.csv';
        downloadLink.href = window.URL.createObjectURL(csvFile);
        downloadLink.style.display = 'none';
        document.body.appendChild(downloadLink);
        downloadLink.click();
    });

    // Search functionality for tables
    $('#tableSearch').on('keyup', function() {
        var value = $(this).val().toLowerCase();
        $('table tbody tr').filter(function() {
            $(this).toggle($(this).text().toLowerCase().indexOf(value) > -1)
        });
    });

    // Priority questions filter
    $('#priorityFilter').on('change', function() {
        var priority = $(this).val();
        if (priority === 'all') {
            $('.priority-section').show();
        } else {
            $('.priority-section').hide();
            $('.priority-' + priority).show();
        }
    });

    // Collapsible sections
    $('.collapse-toggle').on('click', function() {
        var target = $(this).data('target');
        $(target).slideToggle();
        $(this).find('i').toggleClass('fa-chevron-down fa-chevron-up');
    });

    // Dynamic progress bars
    function updateProgressBars() {
        $('.progress-bar').each(function() {
            var width = $(this).data('width');
            $(this).css('width', width + '%');
        });
    }

    // Initialize on page load
    updateProgressBars();

    // Handle window resize for charts
    window.addEventListener('resize', function() {
        if (typeof Plotly !== 'undefined') {
            Plotly.Plots.resize();
        }
    });

    // Print functionality
    $('#printPlan').on('click', function() {
        window.print();
    });

    // Copy to clipboard
    $('.copy-text').on('click', function() {
        var text = $(this).data('text');
        navigator.clipboard.writeText(text).then(function() {
            alert('Copied to clipboard!');
        });
    });

    // Dark mode toggle (optional)
    $('#darkModeToggle').on('change', function() {
        if ($(this).is(':checked')) {
            $('body').addClass('dark-mode');
            localStorage.setItem('darkMode', 'enabled');
        } else {
            $('body').removeClass('dark-mode');
            localStorage.setItem('darkMode', 'disabled');
        }
    });

    // Check for saved dark mode preference
    if (localStorage.getItem('darkMode') === 'enabled') {
        $('#darkModeToggle').prop('checked', true);
        $('body').addClass('dark-mode');
    }
});

// Chart resizing utility
function resizeCharts() {
    if (typeof Plotly !== 'undefined') {
        var charts = document.querySelectorAll('[id^="chart"]');
        charts.forEach(function(chart) {
            Plotly.Plots.resize(chart);
        });
    }
}

// Debounce function for performance
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Window resize debounced
window.addEventListener('resize', debounce(function() {
    resizeCharts();
}, 250));

// Handle page visibility change
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        resizeCharts();
    }
});

// AJAX error handling
$(document).ajaxError(function(event, jqxhr, settings, thrownError) {
    console.error('AJAX Error:', thrownError);
    alert('An error occurred while processing your request. Please try again.');
});