/**
 * Expandable Content Handler
 * Provides "see more/less" functionality for truncated text content
 * Usage: Add class "expandable-content truncated" to any element that should be expandable
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeExpandableContent();
});

function initializeExpandableContent() {
    const expandableItems = document.querySelectorAll('.expandable-content.truncated');

    expandableItems.forEach(function(item, index) {
        // Temporarily remove truncation so we can measure the real content height
        item.classList.remove('truncated');
        item.style.maxHeight = 'none';
        item.style.display = 'block';
        item.style.webkitLineClamp = 'unset';

        var fullHeight = item.scrollHeight;

        // Restore truncation
        item.removeAttribute('style');
        item.classList.add('truncated');

        // Content taller than ~2 lines (48px)? Show the toggle
        if (fullHeight > 50) {
            var toggleBtn = createToggleButton(index);
            item.parentNode.insertBefore(toggleBtn, item.nextSibling);

            toggleBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                toggleExpandableContent(item, toggleBtn);
            });
        } else {
            // Content fits within 2 lines — remove truncation so it shows normally
            item.classList.remove('truncated');
        }
    });
}

function createToggleButton(index) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'expand-toggle-btn';

    var icon = document.createElement('i');
    icon.className = 'fas fa-chevron-down';
    btn.appendChild(icon);

    var text = document.createElement('span');
    text.textContent = 'See More';
    btn.appendChild(text);

    btn.setAttribute('aria-expanded', 'false');
    btn.setAttribute('data-content-id', 'expandable-' + index);
    return btn;
}

function toggleExpandableContent(contentElement, btnElement) {
    var isExpanded = contentElement.classList.contains('expanded');
    var textSpan = btnElement.querySelector('span');

    if (isExpanded) {
        // Collapse
        contentElement.classList.remove('expanded');
        contentElement.classList.add('truncated');
        if (textSpan) textSpan.textContent = 'See More';
        btnElement.setAttribute('aria-expanded', 'false');
    } else {
        // Expand
        contentElement.classList.remove('truncated');
        contentElement.classList.add('expanded');
        if (textSpan) textSpan.textContent = 'See Less';
        btnElement.setAttribute('aria-expanded', 'true');
    }
}
