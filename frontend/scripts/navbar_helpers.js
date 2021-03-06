// Iterate through all navbar anchors and add event listeners
const navAnchors = document.querySelectorAll('#navbarNav li.nav-item a');
for (const anchor of navAnchors) {
    anchor.addEventListener('click', (event) => {
        changeActivePage(event);
    });
}

// Switch Active Page
function changeActivePage(event) {
    document.querySelector('#navbarNav li.active').classList.remove('active');
    event.target.parentNode.classList.add('active');
}
