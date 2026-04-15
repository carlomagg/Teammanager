// Sidebar Modals - Browser Test Script
// Load this in the browser console to verify functionality

// Automated test suite for SidebarModalSystemV2
// Run in the browser console: fetch('/static/js/test_suite.js').then(r=>r.text()).then(eval);
(function() {
    console.log('%c🧪 Sidebar Modals V2 Automated Test Suite', 'font-size:14px; font-weight:bold; color:#319795');

    function el(selector) { return document.querySelector(selector); }
    function els(selector) { return Array.from(document.querySelectorAll(selector)); }

    const results = [];

    function assert(name, cond) {
        results.push({name, pass: !!cond});
        console.log((cond? '✅':'❌') + ' ' + name);
    }

    // Basic DOM checks
    assert('Sidebar exists', el('.sidebar') !== null);
    assert('Seven group modals present', els('.sidebar-group-modal').length === 7);
    assert('Overlay exists', el('.sidebar-modal-overlay') !== null);

    // System init
    assert('System initialized', !!window.sidebarModalSystem);
    const sys = window.sidebarModalSystem;
    assert('Has close method', sys && typeof sys.close === 'function');

    // Helper to dispatch pointer events
    function dispatchPointer(target, type) {
        const ev = new PointerEvent(type, {bubbles: true, cancelable: true});
        target.dispatchEvent(ev);
    }

    // Get sidebar links in order
    const links = els('.sidebar a[data-sm-target]');
    assert('Sidebar links found', links.length >= 7);

    // Automated hover sequence test (1..7)
    (async function hoverSequenceTest(){
        console.log('Running hover sequence test...');
        let pass = true;
        for (let i=0;i<links.length;i++){
            const link = links[i];
            const targetId = link.getAttribute('data-sm-target').replace('#','');
            // pointerover -> expect modal active shortly
            dispatchPointer(link,'pointerover');
            await new Promise(r=>setTimeout(r, 140));
            const modal = document.getElementById(targetId);
            const visible = modal && modal.classList.contains('active');
            console.log(`Hover ${i+1}: ${targetId} visible=${visible}`);
            if (!visible) pass = false;
            // Move pointer out
            dispatchPointer(link,'pointerout');
            await new Promise(r=>setTimeout(r, 180));
            const stillVisible = modal && modal.classList.contains('active');
            if (stillVisible) pass = false;
        }
        assert('Hover sequence (1..N) shows each modal and hides after leave', pass);

        // Click (locked) test
        console.log('Running click (locked) test...');
        const first = links[0];
        first.click();
        await new Promise(r=>setTimeout(r, 120));
        const firstModalId = first.getAttribute('data-sm-target').replace('#','');
        const firstModal = document.getElementById(firstModalId);
        assert('Modal visible after click', firstModal && firstModal.classList.contains('active'));
        assert('Overlay active after click', el('.sidebar-modal-overlay') && el('.sidebar-modal-overlay').classList.contains('active'));

        // Click close button inside modal
        const closeBtn = firstModal && firstModal.querySelector('.sidebar-modal-close');
        if (closeBtn) {
            closeBtn.click();
            await new Promise(r=>setTimeout(r, 360));
            assert('Modal closed after X click', !(firstModal && firstModal.classList.contains('active')));
        } else {
            assert('Close button exists inside modal', false);
        }

        // Ensure overlay removed
        assert('Overlay removed after close', !(el('.sidebar-modal-overlay') && el('.sidebar-modal-overlay').classList.contains('active')));

        // Final summary
        const failed = results.filter(r=>!r.pass).length;
        console.log('%cTest Summary', 'font-weight:bold; color:#319795');
        console.log(`Passed: ${results.length - failed} | Failed: ${failed}`);
        if (failed === 0) console.log('%c✅ ALL TESTS PASS', 'color:green; font-weight:bold');
        else console.log('%c❌ SOME TESTS FAILED', 'color:red; font-weight:bold');
    })();

})();

console.log('%c✅ V2 Test suite loaded. Run fetch("/static/js/test_suite.js").then(r=>r.text()).then(eval); in console.', 'color:#319795');
