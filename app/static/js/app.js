let currentImage = 0;

function changeImage(direction) {
    const images = document.querySelectorAll('.gallery-img');
    if (images.length <= 1) return;

    images[currentImage].classList.remove('active');
    currentImage = (currentImage + direction + images.length) % images.length;
    images[currentImage].classList.add('active');
}
// ===== Живой поиск с подсказками =====
(function () {
    const input = document.getElementById('searchInput');
    const box = document.getElementById('searchSuggest');
    if (!input || !box) return;

    let timer = null;

    input.addEventListener('input', function () {
        const q = input.value.trim();
        clearTimeout(timer);

        if (q.length < 2) {
            box.innerHTML = '';
            box.classList.remove('active');
            return;
        }

        // Дебаунс: ждём паузу 250мс после остановки набора
        timer = setTimeout(async function () {
            try {
                const resp = await fetch('/api/search-suggest?q=' + encodeURIComponent(q));
                const data = await resp.json();
                render(data.results);
            } catch (e) {
                box.innerHTML = '';
                box.classList.remove('active');
            }
        }, 250);
    });

    function render(results) {
        if (!results.length) {
            box.innerHTML = '<div class="suggest-empty">Ничего не найдено</div>';
            box.classList.add('active');
            return;
        }
        box.innerHTML = results.map(function (r) {
            const img = r.image
                ? '<img src="' + r.image + '" alt="">'
                : '<div class="suggest-noimg"></div>';
            return '<a href="/catalog/' + r.slug + '" class="suggest-item">' +
                img +
                '<div class="suggest-info">' +
                '<span class="suggest-name">' + r.name + '</span>' +
                '<span class="suggest-cat">' + r.category + '</span>' +
                '</div>' +
                '<span class="suggest-price">' + r.price + ' ₽</span>' +
                '</a>';
        }).join('');
        box.classList.add('active');
    }

    // Закрывать выпадашку при клике вне её
    document.addEventListener('click', function (e) {
        if (!box.contains(e.target) && e.target !== input) {
            box.classList.remove('active');
        }
    });
})();