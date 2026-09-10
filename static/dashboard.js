/* ==========================================================================
   BUSINESS DASHBOARD — dashboard.js
   Lit les données envoyées par Flask (balise <script id="dashboard-data">)
   et construit les quatre graphiques Chart.js du tableau de bord.
   ========================================================================== */

(function () {
  "use strict";

  /* ------------------------------ Constantes ------------------------------ */
  var COLORS = {
    ink:     "#12213A",
    revenue: "#0E9F6E",
    expense: "#E5484D",
    line:    "#E4E7EC",
    muted:   "#667085"
  };

  // Palette des catégories de dépenses (déclinaisons du rouge vers le navy).
  var CATEGORY_COLORS = [
    "#E5484D", "#F08C4B", "#E8B931", "#5A8DEE",
    "#12213A", "#8B6DF0", "#0E9F6E", "#8C99AD"
  ];

  /* ------------------------------ Utilitaires ------------------------------ */

  // 2500000 -> "2 500 000 FCFA"
  function fcfa(value) {
    var n = Number(value) || 0;
    return n.toLocaleString("fr-FR").replace(/\u202F|\u00A0/g, " ") + " FCFA";
  }

  // Axe vertical : "2,5 M" plutôt que "2 500 000" pour rester lisible.
  function shortAmount(value) {
    var n = Number(value) || 0;
    var abs = Math.abs(n);
    if (abs >= 1e9) return (n / 1e9).toFixed(1).replace(".0", "") + " Md";
    if (abs >= 1e6) return (n / 1e6).toFixed(1).replace(".0", "") + " M";
    if (abs >= 1e3) return Math.round(n / 1e3) + " k";
    return String(n);
  }

  // Dégradé vertical sous une courbe.
  function fillGradient(ctx, area, hex) {
    if (!area) return "transparent";
    var g = ctx.createLinearGradient(0, area.top, 0, area.bottom);
    g.addColorStop(0, hex + "40");
    g.addColorStop(1, hex + "00");
    return g;
  }

  function readData() {
    var tag = document.getElementById("dashboard-data");
    if (!tag) return null;
    try {
      return JSON.parse(tag.textContent || "{}");
    } catch (e) {
      console.error("Données du dashboard illisibles :", e);
      return null;
    }
  }

  function canvas(id) {
    var el = document.getElementById(id);
    return el ? el.getContext("2d") : null;
  }

  /* --------------------------- Options communes --------------------------- */

  function baseOptions(opts) {
    opts = opts || {};
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: COLORS.ink,
          padding: 12,
          cornerRadius: 8,
          displayColors: false,
          titleFont: { weight: "600" },
          callbacks: {
            label: function (item) {
              return fcfa(item.parsed.y !== undefined ? item.parsed.y : item.parsed);
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          border: { color: COLORS.line },
          ticks: { color: COLORS.muted, font: { size: 12 } }
        },
        y: {
          beginAtZero: opts.beginAtZero !== false,
          grid: { color: COLORS.line, drawTicks: false },
          border: { display: false },
          ticks: {
            color: COLORS.muted,
            font: { size: 12 },
            padding: 8,
            callback: function (v) { return shortAmount(v); }
          }
        }
      }
    };
  }

  function lineDataset(label, values, color) {
    return {
      label: label,
      data: values,
      borderColor: color,
      borderWidth: 2.5,
      tension: 0.35,
      pointRadius: 3,
      pointHoverRadius: 6,
      pointBackgroundColor: "#FFFFFF",
      pointBorderColor: color,
      pointBorderWidth: 2,
      fill: true,
      backgroundColor: function (ctx) {
        return fillGradient(ctx.chart.ctx, ctx.chart.chartArea, color);
      }
    };
  }

  /* ------------------------------ Graphiques ------------------------------ */

  function buildCharts(data) {
    var mois = data.mois || [];

    // 1. Évolution du chiffre d'affaires
    var ctxRevenus = canvas("chartRevenus");
    if (ctxRevenus) {
      new Chart(ctxRevenus, {
        type: "line",
        data: {
          labels: mois,
          datasets: [lineDataset("Revenus", data.revenus || [], COLORS.revenue)]
        },
        options: baseOptions()
      });
    }

    // 2. Évolution des dépenses
    var ctxDepenses = canvas("chartDepenses");
    if (ctxDepenses) {
      new Chart(ctxDepenses, {
        type: "line",
        data: {
          labels: mois,
          datasets: [lineDataset("Dépenses", data.depenses || [], COLORS.expense)]
        },
        options: baseOptions()
      });
    }

    // 3. Évolution du bénéfice : barre verte si positif, rouge si négatif.
    var ctxBenefice = canvas("chartBenefice");
    if (ctxBenefice) {
      var benefice = data.benefice || [];
      new Chart(ctxBenefice, {
        type: "bar",
        data: {
          labels: mois,
          datasets: [{
            label: "Bénéfice",
            data: benefice,
            backgroundColor: benefice.map(function (v) {
              return Number(v) >= 0 ? COLORS.revenue : COLORS.expense;
            }),
            borderRadius: 6,
            maxBarThickness: 42
          }]
        },
        options: baseOptions({ beginAtZero: true })
      });
    }

    // 4. Répartition des dépenses par catégorie
    var ctxCategories = canvas("chartCategories");
    if (ctxCategories) {
      var cat = data.categories || { labels: [], montants: [] };
      var total = (cat.montants || []).reduce(function (a, b) {
        return a + (Number(b) || 0);
      }, 0);

      new Chart(ctxCategories, {
        type: "doughnut",
        data: {
          labels: cat.labels || [],
          datasets: [{
            data: cat.montants || [],
            backgroundColor: (cat.labels || []).map(function (_, i) {
              return CATEGORY_COLORS[i % CATEGORY_COLORS.length];
            }),
            borderColor: "#FFFFFF",
            borderWidth: 2,
            hoverOffset: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "62%",
          plugins: {
            legend: {
              position: "bottom",
              labels: {
                color: COLORS.muted,
                boxWidth: 10,
                boxHeight: 10,
                usePointStyle: true,
                pointStyle: "circle",
                padding: 14,
                font: { size: 12.5 }
              }
            },
            tooltip: {
              backgroundColor: COLORS.ink,
              padding: 12,
              cornerRadius: 8,
              displayColors: false,
              callbacks: {
                label: function (item) {
                  var value = Number(item.parsed) || 0;
                  var part = total ? Math.round((value / total) * 100) : 0;
                  return fcfa(value) + "  (" + part + " %)";
                }
              }
            }
          }
        }
      });
    }
  }

  /* ------------------------------ Démarrage ------------------------------ */

  function init() {
    if (typeof Chart === "undefined") {
      console.error("Chart.js n'est pas chargé : les graphiques ne peuvent pas s'afficher.");
      return;
    }

    var data = readData();
    if (!data || !data.mois || !data.mois.length) return; // état vide géré par le template

    // Réglages typographiques globaux, alignés sur la feuille de style.
    Chart.defaults.font.family =
      '"Plus Jakarta Sans", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    Chart.defaults.font.size = 12.5;
    Chart.defaults.color = COLORS.muted;

    buildCharts(data);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
