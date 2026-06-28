/* Оформление заказа: выбор города + карта ПВЗ СДЭК на Яндекс.Картах */
(function () {
    "use strict";

    var cityInput     = document.getElementById("cityInput");
    var suggestBox    = document.getElementById("citySuggest");
    var cityCodeField = document.getElementById("cdekCityCode");
    var cityNameField = document.getElementById("cdekCityName");
    var pvzCodeField  = document.getElementById("cdekPvzCode");
    var pvzAddrField  = document.getElementById("cdekPvzAddress");
    var addressField  = document.getElementById("addressField");
    var mapWrap       = document.getElementById("pvzMapWrap");
    var chosenBox     = document.getElementById("pvzChosen");
    var chosenText    = document.getElementById("pvzChosenText");
    var hint          = document.getElementById("pvzHint");

    if (!cityInput) return;

    var myMap        = null;
    var placemarks   = [];
    var debounceTimer = null;

    // ---------- Подсказки города ----------
    cityInput.addEventListener("input", function () {
        var q = cityInput.value.trim();
        cityCodeField.value = "";
        clearTimeout(debounceTimer);
        if (q.length < 2) { hideSuggest(); return; }  // город — от 2 букв (СДЭК)
        debounceTimer = setTimeout(function () { fetchCities(q); }, 300);
    });

    function fetchCities(q) {
        fetch("/api/cdek/cities?q=" + encodeURIComponent(q))
            .then(function (r) { return r.json(); })
            .then(function (data) { renderSuggest(data.cities || []); })
            .catch(function () { hideSuggest(); });
    }

    function renderSuggest(cities) {
        suggestBox.innerHTML = "";
        if (!cities.length) { hideSuggest(); return; }
        cities.forEach(function (c) {
            var li = document.createElement("li");
            li.className = "city-suggest__item";
            li.textContent = c.full_name || c.city;
            li.addEventListener("click", function () { selectCity(c); });
            suggestBox.appendChild(li);
        });
        suggestBox.hidden = false;
    }

    function hideSuggest() {
        suggestBox.hidden = true;
        suggestBox.innerHTML = "";
    }

    function selectCity(c) {
        cityInput.value     = c.full_name || c.city;
        cityCodeField.value = c.code;
        cityNameField.value = c.city;
        hideSuggest();
        resetChosenPvz();
        loadPoints(c.code);
        calcDelivery(c.code);
    }

    // ---------- Доставка бесплатная: показываем «бесплатно» + срок ----------
    function calcDelivery(cityCode) {
        var box = document.getElementById("deliveryCost");
        if (!box) return;
        box.hidden = false;
        box.innerHTML = '<span class="delivery-cost__free">Доставка СДЭК — <strong>бесплатно</strong></span>';
        // срок доставки показываем, если СДЭК его вернёт (стоимость не показываем)
        fetch("/api/cdek/calculate?city_code=" + encodeURIComponent(cityCode))
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d && d.ok && d.period_min != null && d.period_max != null) {
                    var term = d.period_min === d.period_max
                        ? (d.period_min + " дн.")
                        : (d.period_min + "–" + d.period_max + " дн.");
                    box.innerHTML =
                        '<span class="delivery-cost__free">Доставка СДЭК — <strong>бесплатно</strong></span>' +
                        '<span class="delivery-cost__term"> · срок ' + term + '</span>';
                }
            })
            .catch(function () { /* срок не критичен — оставляем «бесплатно» */ });
    }

    document.addEventListener("click", function (e) {
        if (!e.target.closest(".city-autocomplete")) hideSuggest();
    });

    // ---------- Загрузка ПВЗ ----------
    function loadPoints(cityCode) {
        mapWrap.hidden = false;
        hint.textContent = "Загружаем пункты выдачи…";
        hint.hidden = false;

        fetch("/api/cdek/points?city_code=" + encodeURIComponent(cityCode))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var points = (data.points || []).filter(function (p) {
                    return p.latitude && p.longitude;
                });
                waitForYmaps(function () { renderPoints(points); });
            })
            .catch(function () {
                hint.textContent = "Не удалось загрузить пункты выдачи. Попробуйте позже.";
            });
    }

    function waitForYmaps(cb) {
        if (typeof ymaps !== "undefined") {
            ymaps.ready(function () { ensureMap(); cb(); });
        } else {
            var tries = 0;
            var t = setInterval(function () {
                tries++;
                if (typeof ymaps !== "undefined") {
                    clearInterval(t);
                    ymaps.ready(function () { ensureMap(); cb(); });
                } else if (tries > 50) {
                    clearInterval(t);
                    hint.textContent = "Не удалось загрузить карту. Обновите страницу.";
                }
            }, 200);
        }
    }

    function ensureMap() {
        if (myMap) return;
        myMap = new ymaps.Map("pvzMap", {
            center: [55.75, 37.62],
            zoom: 11,
            controls: ["zoomControl"]
        });
    }

    function clearPlacemarks() {
        placemarks.forEach(function (pm) { myMap.geoObjects.remove(pm); });
        placemarks = [];
    }

    function renderPoints(points) {
        clearPlacemarks();
        if (!points.length) {
            hint.textContent = "В этом городе нет доступных пунктов выдачи.";
            return;
        }
        hint.textContent = "Выберите пункт выдачи на карте.";

        var bounds = [];

        points.forEach(function (p) {
            var lat = parseFloat(p.latitude);
            var lng = parseFloat(p.longitude);
            var pJson = JSON.stringify(p)
                .replace(/\\/g, "\\\\")
                .replace(/'/g, "\\'")
                .replace(/</g, "\\u003c")
                .replace(/>/g, "\\u003e");

            var pm = new ymaps.Placemark([lat, lng], {
                balloonContentHeader: escapeHtml(p.name || "Пункт выдачи"),
                balloonContentBody:
                    "<div style='font-size:13px;line-height:1.5'>" +
                    escapeHtml(p.address || "") +
                    (p.work_time
                        ? "<br><span style='color:#888'>" + escapeHtml(p.work_time) + "</span>"
                        : "") +
                    "</div>" +
                    "<button class='pvz-pick-btn' onclick='__pickPvz(" + pJson + ")'>Выбрать</button>",
                hintContent: escapeHtml(p.name || p.address || "")
            }, {
                preset: "islands#darkGreenDotIcon"
            });

            myMap.geoObjects.add(pm);
            placemarks.push(pm);
            bounds.push([lat, lng]);
        });

        if (bounds.length > 1) {
            myMap.setBounds(ymaps.util.bounds.fromPoints(bounds), {
                checkZoomRange: true,
                zoomMargin: 50
            });
        } else if (bounds.length === 1) {
            myMap.setCenter(bounds[0], 14);
        }
    }

    window.__pickPvz = function (p) {
        choosePvz(p);
        if (myMap) myMap.balloon.close();
    };

    // ---------- Выбор пункта ----------
    function choosePvz(p) {
        pvzCodeField.value = p.code || "";
        var fullAddr = p.address || "";
        pvzAddrField.value = fullAddr;
        addressField.value = (cityNameField.value ? cityNameField.value + ", " : "") + fullAddr;
        chosenText.textContent = (p.name ? p.name + " — " : "") + fullAddr;
        chosenBox.hidden = false;
        hint.hidden = true;
    }

    function resetChosenPvz() {
        pvzCodeField.value = "";
        pvzAddrField.value = "";
        addressField.value = "";
        chosenBox.hidden = true;
        if (hint) hint.hidden = false;
    }

    // ---------- Валидация ----------
    var form = document.getElementById("checkoutForm");
    form.addEventListener("submit", function (e) {
        if (!cityCodeField.value) {
            e.preventDefault();
            alert("Пожалуйста, выберите город из списка подсказок.");
            cityInput.focus();
            return;
        }
        if (!pvzCodeField.value) {
            e.preventDefault();
            alert("Пожалуйста, выберите пункт выдачи на карте.");
        }
    });

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }
})();