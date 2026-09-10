document.addEventListener("DOMContentLoaded", function () {

    // ÉVOLUTION FINANCIÈRE

    const evolutionCanvas = document.getElementById(
        "reportsEvolutionChart"
    );

    if (evolutionCanvas) {

        new Chart(evolutionCanvas, {
            type: "line",

            data: {
                labels: reportMonths,

                datasets: [
                    {
                        label: "Revenus",
                        data: reportRevenus,
                        tension: 0.3
                    },
                    {
                        label: "Dépenses",
                        data: reportDepenses,
                        tension: 0.3
                    }
                ]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        position: "bottom"
                    }
                }
            }
        });
    }


    // DÉPENSES PAR CATÉGORIE

    const categoriesCanvas = document.getElementById(
        "reportsCategoriesChart"
    );

    if (categoriesCanvas) {

        new Chart(categoriesCanvas, {
            type: "doughnut",

            data: {
                labels: reportCategoriesLabels,

                datasets: [
                    {
                        data: reportCategoriesValues
                    }
                ]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        position: "bottom"
                    }
                }
            }
        });
    }

});