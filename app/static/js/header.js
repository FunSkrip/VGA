// Фиксированная шапка с анимацией
function initFixedHeader() {
    const header = document.querySelector('header');
    if (!header) return;

    let lastScroll = 0;
    const headerHeight = header.offsetHeight;

    document.documentElement.style.setProperty(
        '--header-height',
        `${headerHeight}px`
    );

    window.addEventListener('scroll', function() {
        const currentScroll = window.pageYOffset;

        if (currentScroll > lastScroll && currentScroll > 100) {
            header.classList.add('header-hidden');
        } else {
            header.classList.remove('header-hidden');
        }

        lastScroll = currentScroll;
    });
}

document.addEventListener('DOMContentLoaded', initFixedHeader);