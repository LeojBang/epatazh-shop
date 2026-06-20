let currentImage = 0;

function changeImage(direction) {
    const images = document.querySelectorAll('.gallery-img');
    if (images.length <= 1) return;

    images[currentImage].classList.remove('active');
    currentImage = (currentImage + direction + images.length) % images.length;
    images[currentImage].classList.add('active');
}