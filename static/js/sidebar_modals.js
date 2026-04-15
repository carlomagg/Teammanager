/*
 Sidebar Modal System V2 - Clean rewrite
*/

class SidebarModalSystemV2 {
    constructor() {
        this.sidebar = document.querySelector('.sidebar');
        this.overlay = document.querySelector('.sidebar-modal-overlay');

        this.currentModal = null;
        this.currentTrigger = null;
        this.locked = false;

        this._token = 0;
        this._openTimer = null;
        this._closeTimer = null;
        this._blockUntil = 0;

        this._bound = {
            pointerover: this._onSidebarPointerOver.bind(this),
            pointerout: this._onSidebarPointerOut.bind(this),
            click: this._onSidebarClick.bind(this),
            overlayClick: this._onOverlayClick.bind(this),
            keydown: this._onKeyDown.bind(this)
        };

        this._modalHandlers = { enter: null, leave: null };

        this.init();
    }

    init() {
        if (window.sidebarModalSystem && typeof window.sidebarModalSystem.destroy === 'function') {
            window.sidebarModalSystem.destroy();
        }

        if (this.sidebar) {
            // Move bootstrap modal attributes to custom attributes to avoid Bootstrap interference
            this.sidebar.querySelectorAll('a[data-bs-target]').forEach(link => {
                const target = link.getAttribute('data-bs-target');
                if (target) {
                    link.setAttribute('data-sm-target', target);
                    link.removeAttribute('data-bs-target');
                }
                // Remove bootstrap toggle to prevent Bootstrap modal from handling clicks
                if (link.hasAttribute('data-bs-toggle')) link.removeAttribute('data-bs-toggle');
            });

            this.sidebar.addEventListener('pointerover', this._bound.pointerover);
            this.sidebar.addEventListener('pointerout', this._bound.pointerout);
            this.sidebar.addEventListener('click', this._bound.click);
        }

        if (this.overlay) {
            this.overlay.addEventListener('click', this._bound.overlayClick);
        }

        document.addEventListener('keydown', this._bound.keydown);
        window.addEventListener('resize', () => this._onWindowResize());

        window.sidebarModalSystem = this;
    }

    _onWindowResize() {
        // Reposition modal if screen size changes
        if (this.currentModal && this.currentTrigger) {
            this._position(this.currentModal, this.currentTrigger);
        }
    }

    // Delegated pointerover -> schedule preview open
    _onSidebarPointerOver(e) {
        const link = e.target.closest('a[data-sm-target]');
        if (!link) return;
        const from = e.relatedTarget;
        if (from && link.contains(from)) return;
        const targetId = link.getAttribute('data-sm-target');
        if (!targetId) return;

        if (Date.now() < this._blockUntil) return;

        this._token++;
        const token = this._token;
        clearTimeout(this._openTimer);
        this._openTimer = setTimeout(() => {
            if (token !== this._token) return;
            this._openModal(targetId.replace('#',''), link, false);
        }, 80);
    }

    // Delegated pointerout -> schedule preview close
    _onSidebarPointerOut(e) {
        const link = e.target.closest('a[data-sm-target]');
        if (!link) return;
        const to = e.relatedTarget;
        if (to && link.contains(to)) return;

        this._token++;
        clearTimeout(this._openTimer);
        if (!this.locked && this.currentModal) {
            const token = this._token;
            this._closeTimer = setTimeout(() => {
                if (token !== this._token) return;
                if (!this.locked) this._closeModal(false);
            }, 120);
        }
    }

    _onSidebarClick(e) {
        const link = e.target.closest('a[data-sm-target]');
        if (!link) return;
        e.preventDefault();
        e.stopPropagation();
        if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
        this._token++;
        clearTimeout(this._openTimer);
        clearTimeout(this._closeTimer);
        this._openModal(link.getAttribute('data-sm-target').replace('#',''), link, true);
    }

    _onOverlayClick() { this._closeModal(true); }
    _onKeyDown(e) { if (e.key === 'Escape') this._closeModal(true); }

    // --- open/close core ---
    _openModal(id, trigger, locked) {
        if (Date.now() < this._blockUntil) return;
        const modal = document.getElementById(id);
        if (!modal) return;

        // if another modal open, close it immediately
        if (this.currentModal && this.currentModal !== modal) {
            this._forceCloseCurrent();
        }

        this.currentModal = modal;
        this.currentTrigger = trigger || null;
        this.locked = !!locked;

        // overlay
        if (this.overlay) {
            if (this.locked) this.overlay.classList.add('active'); else this.overlay.classList.remove('active');
        }

        modal.classList.remove('closing');
        modal.classList.add('active');
        this._position(modal, this.currentTrigger);

        // add modal pointer handlers for preview mode
        this._removeModalHandlers();
        if (!this.locked) {
            this._modalHandlers.enter = () => { this._token++; clearTimeout(this._closeTimer); };
            this._modalHandlers.leave = (evt) => {
                const to = evt.relatedTarget;
                if (to && this.currentTrigger && this.currentTrigger.contains(to)) return;
                this._token++;
                const token = this._token;
                this._closeTimer = setTimeout(() => { if (token!==this._token) return; if (!this.locked) this._closeModal(false); }, 120);
            };
            modal.addEventListener('pointerenter', this._modalHandlers.enter);
            modal.addEventListener('pointerleave', this._modalHandlers.leave);
        }
    }

    _closeModal(force) {
        if (this.locked && !force) return;

        // Immediately block new opens to avoid reopen race
        this._blockUntil = Date.now() + 500;

        // Invalidate pending timers and handlers
        this._token++;
        clearTimeout(this._openTimer);
        clearTimeout(this._closeTimer);

        if (!this.currentModal) return;

        const modal = this.currentModal;

        // Remove modal handlers now to prevent pointer events from retriggering
        this._removeModalHandlers();

        // Begin closing animation and hide overlay immediately
        modal.classList.add('closing');
        if (this.overlay) this.overlay.classList.remove('active');

        // Also remove active immediately to hide visual state (prevents flicker)
        modal.classList.remove('active');

        setTimeout(() => {
            modal.classList.remove('closing');
            // Final cleanup
            this.currentModal = null;
            this.currentTrigger = null;
            this.locked = false;
            // extend block slightly in case of stray events
            this._blockUntil = Date.now() + 300;
        }, 260);
    }

    _forceCloseCurrent() {
        if (!this.currentModal) return;
        // remove handlers and classes synchronously
        this._removeModalHandlers();
        this.currentModal.classList.remove('active','closing');
        this.currentModal = null;
        this.currentTrigger = null;
        this.locked = false;
    }

    _removeModalHandlers() {
        if (!this.currentModal) return;
        if (this._modalHandlers.enter) {
            this.currentModal.removeEventListener('pointerenter', this._modalHandlers.enter);
            this._modalHandlers.enter = null;
        }
        if (this._modalHandlers.leave) {
            this.currentModal.removeEventListener('pointerleave', this._modalHandlers.leave);
            this._modalHandlers.leave = null;
        }
    }

    _position(modal, trigger) {
        if (!modal || !trigger) return;

        // Check if we're on mobile/small screen (< 851px)
        const isMobile = window.innerWidth <= 850;

        if (isMobile) {
            // MOBILE: CSS handles positioning with transform: translate(-50%, -50%)
            // No JavaScript positioning needed for mobile
            modal.style.left = '';
            modal.style.top = '';
            modal.style.transform = '';
            const ptr = modal.querySelector('.sidebar-modal-pointer');
            if (ptr) ptr.style.display = 'none';
            return;
        }

        // DESKTOP: Position relative to trigger (sidebar item)
        const triggerRect = trigger.getBoundingClientRect();
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return;
        const sidebarRect = sidebar.getBoundingClientRect();
        const left = sidebarRect.width + 15;
        let top = triggerRect.top - 10;
        const mh = modal.offsetHeight;
        const wh = window.innerHeight;
        if (top + mh > wh - 20) top = wh - mh - 20;
        if (top < 70) top = 70;
        modal.style.left = left + 'px';
        modal.style.top = top + 'px';
        modal.style.transform = '';
        const ptr = modal.querySelector('.sidebar-modal-pointer');
        if (ptr) {
            ptr.style.display = '';
            ptr.style.top = (triggerRect.top - top + (triggerRect.height/2) - 6) + 'px';
        }
    }

    // Public close used by template
    close(force=true) { this._closeModal(!!force); }

    destroy() {
        if (this.sidebar) {
            this.sidebar.removeEventListener('pointerover', this._bound.pointerover);
            this.sidebar.removeEventListener('pointerout', this._bound.pointerout);
            this.sidebar.removeEventListener('click', this._bound.click);
        }
        if (this.overlay) this.overlay.removeEventListener('click', this._bound.overlayClick);
        document.removeEventListener('keydown', this._bound.keydown);
        window.removeEventListener('resize', () => this._onWindowResize());
        clearTimeout(this._openTimer);
        clearTimeout(this._closeTimer);
        this._removeModalHandlers();
        if (window.sidebarModalSystem === this) delete window.sidebarModalSystem;
    }
}

function closeSidebarModal(){ if (window.sidebarModalSystem) window.sidebarModalSystem.close(true); }

document.addEventListener('DOMContentLoaded', ()=> new SidebarModalSystemV2());



