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

// ===== Вкладки "Мои заказы" =====
(function () {
    const tabs = document.querySelectorAll('.orders-tab');
    if (!tabs.length) return;

    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            const target = tab.dataset.tab;

            // Переключаем активную кнопку
            tabs.forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');

            // Показываем нужную панель, прячем другую
            document.getElementById('panel-active').style.display =
                target === 'active' ? 'block' : 'none';
            document.getElementById('panel-completed').style.display =
                target === 'completed' ? 'block' : 'none';
        });
    });
})();
function getCookie(name) {
    const match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
}

async function toggleFavorite(event, productId) {
    event.preventDefault();
    event.stopPropagation();
    const btn = event.currentTarget;
    try {
        const resp = await fetch(`/favorites/toggle/${productId}`, {
            method: 'POST',
            headers: { 'X-CSRF-Token': getCookie('csrf_token') },
        });
        if (resp.status === 401) {
            window.location.href = '/login';
            return;
        }
        const data = await resp.json();
        btn.classList.toggle('is-favorite', data.favorite);

        // Если внутри есть отдельные span'ы (страница товара) — обновляем их
        const icon = btn.querySelector('.favorite-icon');
        const label = btn.querySelector('.favorite-label');
        if (icon) {
            icon.textContent = data.favorite ? '♥' : '♡';
        }
        if (label) {
            label.textContent = data.favorite ? 'В избранном' : 'В избранное';
        }
        // Если span'ов нет (карточка — только сердечко) — меняем всю кнопку
        if (!icon && !label) {
            btn.textContent = data.favorite ? '♥' : '♡';
        }
    } catch (e) {
        console.error('Ошибка избранного:', e);
    }
}

// --- Листание фото на карточках каталога наведением курсора ---
(function () {
    function setActive(gallery, idx) {
        gallery.querySelectorAll('.card-img').forEach(function (img) {
            img.classList.toggle('active', img.dataset.idx === String(idx));
        });
        gallery.querySelectorAll('.card-dot').forEach(function (dot) {
            dot.classList.toggle('active', dot.dataset.idx === String(idx));
        });
    }

    document.addEventListener('mouseover', function (e) {
        var zone = e.target.closest('.card-hover-zone');
        if (!zone) return;
        var gallery = zone.closest('.card-gallery');
        if (!gallery) return;
        setActive(gallery, zone.dataset.idx);
    });

    // Когда курсор уходит с карточки — возвращаем первое фото
    document.addEventListener('mouseleave', function (e) {
        var gallery = e.target.closest ? e.target.closest('.card-gallery') : null;
        if (gallery) setActive(gallery, 0);
    }, true);
})();