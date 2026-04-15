// Browser Notification Support
(function() {
    'use strict';

    // Check if browser supports notifications
    if (!('Notification' in window)) {
        console.log('This browser does not support desktop notifications');
        return;
    }

    // Request permission on page load if not already granted or denied
    function requestNotificationPermission() {
        if (Notification.permission === 'default') {
            Notification.requestPermission().then(function(permission) {
                if (permission === 'granted') {
                    console.log('Notification permission granted');
                } else {
                    console.log('Notification permission denied');
                }
            });
        }
    }

    // Show a browser notification
    function showBrowserNotification(title, options) {
        if (Notification.permission === 'granted') {
            const notification = new Notification(title, options);
            
            // Auto-close after 10 seconds
            setTimeout(function() {
                notification.close();
            }, 10000);
            
            return notification;
        } else if (Notification.permission === 'default') {
            // Request permission and show notification if granted
            Notification.requestPermission().then(function(permission) {
                if (permission === 'granted') {
                    const notification = new Notification(title, options);
                    setTimeout(function() {
                        notification.close();
                    }, 10000);
                    return notification;
                }
            });
        }
        return null;
    }

    // Create notification from data
    function createNotification(data) {
        const options = {
            body: data.message || '',
            icon: data.icon || '/static/favicon_io/android-chrome-192x192.png',
            badge: data.badge || '/static/favicon_io/favicon-32x32.png',
            tag: 'notification-' + data.id,  // Use notification ID as tag to prevent duplicates
            requireInteraction: false,
            silent: false,
            renotify: false,  // Don't re-alert for same tag
            data: {
                url: data.url || '/notifications/',
                notificationId: data.id
            }
        };

        const notification = showBrowserNotification(data.title, options);
        
        if (notification) {
            // Handle notification click
            notification.onclick = function(event) {
                event.preventDefault();
                window.focus();
                if (data.url) {
                    window.location.href = data.url;
                }
                notification.close();
            };
        }
    }

    // Poll for new notifications
    let lastNotificationCheck = Date.now();
    let pollingInterval = null;
    
    // Track which notifications we've already shown (persist in localStorage)
    function getShownNotificationIds() {
        try {
            const stored = localStorage.getItem('shownNotificationIds');
            if (stored) {
                const ids = JSON.parse(stored);
                // Only keep IDs from the last 24 hours to prevent localStorage from growing too large
                const oneDayAgo = Date.now() - (24 * 60 * 60 * 1000);
                const filtered = ids.filter(item => item.timestamp > oneDayAgo);
                return new Set(filtered.map(item => item.id));
            }
        } catch (e) {
            console.error('Error loading shown notification IDs:', e);
        }
        return new Set();
    }
    
    function saveShownNotificationId(id) {
        try {
            const stored = localStorage.getItem('shownNotificationIds');
            let ids = stored ? JSON.parse(stored) : [];
            
            // Add new ID with timestamp
            ids.push({ id: id, timestamp: Date.now() });
            
            // Only keep IDs from the last 24 hours
            const oneDayAgo = Date.now() - (24 * 60 * 60 * 1000);
            ids = ids.filter(item => item.timestamp > oneDayAgo);
            
            localStorage.setItem('shownNotificationIds', JSON.stringify(ids));
        } catch (e) {
            console.error('Error saving shown notification ID:', e);
        }
    }
    
    let shownNotificationIds = getShownNotificationIds();

    function checkForNewNotifications() {
        // Only check if user is authenticated
        if (!document.body.classList.contains('authenticated')) {
            return;
        }

        fetch('/api/notifications/check/', {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        })
        .then(response => response.json())
        .then(data => {
            console.log('Notification check response:', data);
            if (data.notifications && data.notifications.length > 0) {
                console.log(`Found ${data.notifications.length} new notifications`);
                data.notifications.forEach(function(notif) {
                    // Only show if we haven't shown this notification before
                    if (!shownNotificationIds.has(notif.id)) {
                        console.log('Showing notification:', notif.id, notif.title);
                        createNotification(notif);
                        shownNotificationIds.add(notif.id);
                        saveShownNotificationId(notif.id);
                    } else {
                        console.log('Skipping duplicate notification:', notif.id);
                    }
                });
                lastNotificationCheck = Date.now();
                
                // Update badge count
                updateNotificationBadge(data.total_count);
            } else {
                console.log('No new notifications');
            }
        })
        .catch(error => {
            console.error('Error checking notifications:', error);
        });
    }

    function updateNotificationBadge(count) {
        const badge = document.querySelector('.notification-badge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline';
            } else {
                badge.style.display = 'none';
            }
        }
    }

    // Start polling for notifications (every 10 seconds for faster updates)
    function startNotificationPolling() {
        if (pollingInterval) {
            clearInterval(pollingInterval);
        }
        
        // Check immediately
        checkForNewNotifications();
        
        // Then check every 10 seconds (faster than before)
        pollingInterval = setInterval(checkForNewNotifications, 10000);
    }

    // Stop polling
    function stopNotificationPolling() {
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    }

    // Initialize on page load
    document.addEventListener('DOMContentLoaded', function() {
        // Request permission if user is authenticated
        if (document.body.classList.contains('authenticated')) {
            requestNotificationPermission();
            
            // Start polling after a short delay
            setTimeout(startNotificationPolling, 2000);
        }
        
        // Stop polling when page is hidden
        document.addEventListener('visibilitychange', function() {
            if (document.hidden) {
                stopNotificationPolling();
            } else {
                startNotificationPolling();
            }
        });
    });

    // Expose functions globally
    window.BrowserNotifications = {
        request: requestNotificationPermission,
        show: createNotification,
        startPolling: startNotificationPolling,
        stopPolling: stopNotificationPolling
    };
})();
