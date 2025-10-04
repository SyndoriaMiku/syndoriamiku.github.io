$(document).ready(function () {
    let thisYear = new Date().getFullYear();
    let thisMonth = new Date().getMonth() + 1;
    $("#year-select").val(thisYear);
    $("#month-select").val(thisMonth);

    let page = 1;
    let pageSize = 10;
    let totalPages = 1;

    loadRank(thisYear, thisMonth, page, pageSize);

    //Search button
    $("#load-rank").click(function () {
        let year = $("#year-select").val();
        let month = $("#month-select").val();
        loadRank(year, month, page, pageSize);
    });

    //Go to page button
    $(document).on('click', '#goto-go', function (e) {
        e.preventDefault();
    
        const page = parseInt($('#goto-page').val());
        const year = parseInt($('#year-select').val());
        const month = parseInt($('#month-select').val());
        const pageSize = parseInt($('#pagination').data('pagesize')) || 10;
        const totalPages = parseInt($('#pagination').data('totalpages')) || 1;
    
        if (page >= 1 && page <= totalPages) {
            loadRank(year, month, page, pageSize);
        } else {
            alert('Số trang không hợp lệ!');
        }
    }); 
    


    
});


/**
 * Load ranking data from API
 * @param {*} year 
 * @param {*} month 
 * @param {*} page 
 * @param {*} pageSize 
 */
function loadRank(year, month, page, pageSize) {
    $("#rank-table tbody").empty();
    showSpinner(); // Show loading spinner
    
    $.ajax({
        type: "GET",
        url: `https://gremory.pythonanywhere.com/api/ranking/monthly/?year=${year}&month=${month}&page=${page}&pageSize=${pageSize}`,
        success: function (response) {
            hideSpinner(); // Hide loading spinner
            for (let i = 0; i < response.results.length; i++) {
                //Calculate rank
                let startRank = (response.current_page - 1) * response.page_size + 1;
                //Get data
                let rank = startRank + i;
                let playerName = response.results[i].nickname;
                let username = response.results[i].username || playerName; // Use username if available, fallback to nickname
                let totalPoints = response.results[i].ranking_earned;
                //Build HTML with double-click functionality
                let row = $(`<tr class="ranking-row" data-username="${username}" style="cursor: pointer;">
                    <td>${rank}</td>
                    <td>${playerName}</td>
                    <td>${totalPoints}</td>
                </tr>`);
                
                // Add double-click event to redirect to search page
                row.on('dblclick', function() {
                    const username = $(this).data('username');
                    const year = $("#year-select").val();
                    const month = $("#month-select").val();
                    
                    // Redirect to search page with query parameters
                    window.location.href = `search.html?username=${encodeURIComponent(username)}&year=${year}&month=${month}`;
                });
                
                //Append HTML to table
                $("#rank-table tbody").append(row);
            }
            //Append pagination
            loadPagination(response.current_page, response.total_pages, response.year, response.month, pageSize);
            
            
        },
        error: function(xhr) {
            hideSpinner(); // Hide spinner on error
            showNoticeDialog("Có lỗi xảy ra khi tải dữ liệu. Vui lòng thử lại!");
        }
    });
}

/** * Load pagination
 * @param {*} currentPage 
 * @param {*} totalPages 
 * @param {*} year 
 * @param {*} month 
 * @param {*} pageSize 
 */

function loadPagination(currentPage, totalPages, year, month, pageSize) {
    let pagination = $('#pagination');
    pagination.empty();
    // First and previous button
    if (currentPage > 1) {
        if (currentPage > 2) {
            pagination.append(`<li class="page-item arrow">
                <a class="page-link" href="#" onclick="loadRank(${year}, ${month}, 1, ${pageSize})">First</a>
                </li>`);
        }
        pagination.append(`<li class="page-item arrow">
            <a class="page-link" href="#" onclick="loadRank(${year}, ${month}, ${currentPage - 1}, ${pageSize})">Previous</a>
            </li>`);
    }
    // Current page
    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, currentPage + 2);

    for (let i = startPage; i <= endPage; i++) {
        pagination.append(`
            <li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="loadRank(${year}, ${month}, ${i}, ${pageSize})">${i}</a>
            </li>
        `);
    }

    // Next and last button
    if (currentPage < totalPages) {
        if (currentPage < totalPages - 1) {
            pagination.append(`<li class="page-item arrow"" >
                <a class="page-link" href="#" onclick="loadRank(${year}, ${month}, ${currentPage + 1}, ${pageSize})">Next</a>
                </li>`);
        }
        pagination.append(`<li class="page-item arrow">
            <a class="page-link" href="#" onclick="loadRank(${year}, ${month}, ${totalPages}, ${pageSize})">Last</a>
            </li>`);
    }

    pagination.append(`
        <li class="page-item ml-2 goto-wrapper">
            <input type="number" id="goto-page" min="1" max="${totalPages}" value="${currentPage}" class="form-control goto-input" />
        </li>
        <li class="page-item goto-wrapper">
            <button class="page-link goto-btn" id="goto-go">Go</button>
        </li>
    `);


}