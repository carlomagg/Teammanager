/**
 * Browser Notifications System
 * Polls for new notifications and shows Chrome/system notifications automatically.
 * Permission is requested automatically on page load for authenticated users.
 */
(function () {
    'use strict';

    // ── Configuration ──
    const POLL_INTERVAL = 30000;      // Poll every 30 seconds
    const CHECK_URL = '/api/notifications/check/';
    const NOTIFICATION_ICON = '/static/Team Manager icon.png';
    const NOTIFICATION_TAG_PREFIX = 'tm-notif-';

    // Track shown notifications to avoid duplicates
    const shownNotifications = new Set();
    let pollTimer = null;

    // ── Permission Handling ──

    /**
     * Request notification permission automatically.
     * Shows a soft in-app prompt first if permission is 'default' (not yet asked).
     */
    function requestPermission() {
        if (!('Notification' in window)) {
            console.log('[BrowserNotif] Browser does not support notifications');
            return;
        }

        if (Notification.permission === 'granted') {
            // Already granted — start polling immediately
            startPolling();
            return;
        }

        if (Notification.permission === 'denied') {
            console.log('[BrowserNotif] Notifications denied by user');
            // Still poll for badge count updates, just won't show system notifications
            startPolling();
            return;
        }

        // Permission is 'default' — auto-request with a slight delay
        // so the page loads first and the prompt feels natural
        setTimeout(function () {
            showSoftPrompt();
        }, 3000);
    }

    /**
     * Show a soft in-app banner prompting the user to enable notifications,
     * then trigger the actual browser permission dialog.
     */
    function showSoftPrompt() {
        // Check if we already asked recently (once per session)
        if (sessionStorage.getItem('notif_prompt_shown')) {
            startPolling();
            return;
        }
        sessionStorage.setItem('notif_prompt_shown', '1');

        // Create a subtle toast/banner
        var banner = document.createElement('div');
        banner.id = 'notif-permission-banner';
        banner.innerHTML = 
            '<div style="position:fixed;bottom:20px;right:20px;z-index:99999;' +
            'background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;' +
            'padding:16px 24px;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.3);' +
            'display:flex;align-items:center;gap:12px;max-width:400px;' +
            'font-family:Inter,system-ui,sans-serif;font-size:14px;' +
            'animation:slideInRight 0.4s ease-out;">' +
            '<i class="fas fa-bell" style="font-size:24px;color:#319795;"></i>' +
            '<div style="flex:1;">' +
            '<strong style="display:block;margin-bottom:4px;">Enable Notifications</strong>' +
            '<span style="opacity:0.85;font-size:13px;">Get instant alerts for memos, tasks & events</span>' +
            '</div>' +
            '<button id="notif-enable-btn" style="background:#319795;color:#fff;border:none;' +
            'padding:8px 16px;border-radius:8px;cursor:pointer;font-weight:600;font-size:13px;' +
            'white-space:nowrap;">Enable</button>' +
            '<button id="notif-dismiss-btn" style="background:transparent;color:#fff;border:none;' +
            'cursor:pointer;font-size:18px;opacity:0.6;padding:4px 8px;">&times;</button>' +
            '</div>';

        // Add slide-in animation
        var style = document.createElement('style');
        style.textContent = '@keyframes slideInRight{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}';
        document.head.appendChild(style);
        document.body.appendChild(banner);

        // Enable button — triggers the actual browser permission dialog
        document.getElementById('notif-enable-btn').addEventListener('click', function () {
            Notification.requestPermission().then(function (permission) {
                banner.remove();
                if (permission === 'granted') {
                    // Show a welcome notification
                    showSystemNotification(
                        'Notifications Enabled! ✅',
                        'You will now receive alerts for memos, tasks and events.',
                        null
                    );
                }
                startPolling();
            });
        });

        // Dismiss button
        document.getElementById('notif-dismiss-btn').addEventListener('click', function () {
            banner.remove();
            startPolling(); // Still poll for badge updates
        });

        // Auto-dismiss after 30 seconds
        setTimeout(function () {
            if (document.getElementById('notif-permission-banner')) {
                banner.remove();
                startPolling();
            }
        }, 30000);
    }

    // ── Polling ──

    function startPolling() {
        // Initial check
        checkForNewNotifications();
        // Set up interval
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = setInterval(checkForNewNotifications, POLL_INTERVAL);
    }

    function checkForNewNotifications() {
        fetch(CHECK_URL, {
            method: 'GET',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(function (response) {
            if (!response.ok) throw new Error('Network error');
            return response.json();
        })
        .then(function (data) {
            if (!data.success) return;

            // Update badge count in the navbar
            updateBadge(data.total_count);

            // Show browser notifications for new items
            if (data.notifications && data.notifications.length > 0) {
                data.notifications.forEach(function (notif) {
                    if (!shownNotifications.has(notif.id)) {
                        shownNotifications.add(notif.id);
                        showSystemNotification(
                            notif.title,
                            notif.message,
                            notif.url
                        );
                    }
                });
            }
        })
        .catch(function (err) {
            // Silent fail — don't spam the console
            console.debug('[BrowserNotif] Poll error:', err.message);
        });
    }

    // ── System Notification ──

    function showSystemNotification(title, body, url) {
        if (!('Notification' in window) || Notification.permission !== 'granted') {
            return;
        }

        try {
            var notif = new Notification(title, {
                body: body,
                icon: NOTIFICATION_ICON,
                badge: NOTIFICATION_ICON,
                tag: NOTIFICATION_TAG_PREFIX + Date.now(),
                requireInteraction: false,
                silent: false
            });

            // Click handler — navigate to the notification's target URL
            if (url) {
                notif.onclick = function (event) {
                    event.preventDefault();
                    window.focus();
                    window.location.href = url;
                    notif.close();
                };
            }

            // Auto-close after 8 seconds
            setTimeout(function () {
                notif.close();
            }, 8000);

        } catch (e) {
            console.debug('[BrowserNotif] Failed to create notification:', e);
        }
    }

    // ── Badge Update ──

    function updateBadge(count) {
        // Update the bell icon badge in the navbar
        var badges = document.querySelectorAll('.notification-badge, #notification-count');
        badges.forEach(function (badge) {
            if (count > 0) {
                badge.textContent = count > 99 ? '99+' : count;
                badge.style.display = '';
            } else {
                badge.style.display = 'none';
            }
        });
    }

    // ── Initialization ──

    // Only run for authenticated users
    document.addEventListener('DOMContentLoaded', function () {
        // Check if user is authenticated (body has class set in base.html)
        if (document.body.classList.contains('authenticated')) {
            requestPermission();
        }
    });

    // Clean up on page unload
    window.addEventListener('beforeunload', function () {
        if (pollTimer) clearInterval(pollTimer);
    });

})();
