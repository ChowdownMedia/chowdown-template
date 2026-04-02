/* ==========================================================================
   Chowdown Main JS
   Single JS file for the entire template system.
   Vanilla JS only — zero external dependencies, no jQuery.
   Defer safe — all initialization runs on DOMContentLoaded.

   Modules:
     1. Nav — mobile toggle, dropdowns, scroll state, outside click close
     2. Hero Video — play/pause toggle with icon swap
     3. Carousels — shared logic for reviews + specials
     4. Map — click-to-load iframe injection
     5. Reviews Worker — dynamic fetch + fallback
     6. Modals — open/close, overlay click, ESC, focus trap
     7. Accessibility — reduced motion, focus management
   ========================================================================== */

document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;


  /* ========================================================================
     1. NAV
     ======================================================================== */

  (function initNav() {
    var header = document.getElementById('site-header');
    var toggle = document.getElementById('nav-toggle');
    var menu = document.getElementById('mobile-menu');
    if (!header) return;

    // Scroll state
    function onScroll() {
      header.classList.toggle('scrolled', window.scrollY > 50);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    // Mobile toggle
    if (toggle && menu) {
      toggle.addEventListener('click', function () {
        var isOpen = menu.classList.toggle('open');
        toggle.classList.toggle('active', isOpen);
        toggle.setAttribute('aria-expanded', isOpen);
      });

      // Close on outside click
      document.addEventListener('click', function (e) {
        if (menu.classList.contains('open') &&
            !menu.contains(e.target) &&
            !toggle.contains(e.target)) {
          menu.classList.remove('open');
          toggle.classList.remove('active');
          toggle.setAttribute('aria-expanded', 'false');
        }
      });
    }

    // Mobile dropdowns
    var dropdownToggles = document.querySelectorAll('.mobile-dropdown-toggle');
    for (var i = 0; i < dropdownToggles.length; i++) {
      dropdownToggles[i].addEventListener('click', function (e) {
        e.preventDefault();
        this.parentElement.classList.toggle('open');
      });
    }
  })();


  /* ========================================================================
     2. HERO VIDEO
     ======================================================================== */

  (function initHeroVideo() {
    var video = document.querySelector('.hero-video');
    var toggleBtn = document.getElementById('hero-video-toggle');
    if (!video || !toggleBtn) return;

    var icon = toggleBtn.querySelector('.icon');
    var playing = true;

    // Respect reduced motion
    if (prefersReducedMotion) {
      video.pause();
      playing = false;
      swapIcon(icon, 'icon-pause', 'icon-play');
      toggleBtn.setAttribute('aria-label', 'Play video');
    }

    toggleBtn.addEventListener('click', function () {
      if (playing) {
        video.pause();
        swapIcon(icon, 'icon-pause', 'icon-play');
        toggleBtn.setAttribute('aria-label', 'Play video');
      } else {
        video.play();
        swapIcon(icon, 'icon-play', 'icon-pause');
        toggleBtn.setAttribute('aria-label', 'Pause video');
      }
      playing = !playing;
    });

    // Fade out poster when video starts playing
    video.addEventListener('playing', function () {
      var hero = video.closest('.hero');
      if (hero) hero.classList.add('video-playing');
    });
  })();


  /* ========================================================================
     3. CAROUSELS (shared logic for reviews + specials)
     ======================================================================== */

  function Carousel(containerId, opts) {
    var container = document.getElementById(containerId);
    if (!container) return null;

    var slides = container.querySelectorAll(opts.slideSelector);
    if (!slides.length) return null;

    var dotsContainer = document.getElementById(opts.dotsId);
    var prevBtn = document.getElementById(opts.prevId);
    var nextBtn = document.getElementById(opts.nextId);
    var pauseBtn = document.getElementById(opts.pauseId);

    var current = 0;
    var timer = null;
    var paused = false;
    var interval = opts.interval || 5000;

    function show(index) {
      // Refresh slide list (may have changed via dynamic injection)
      slides = container.querySelectorAll(opts.slideSelector);
      if (!slides.length) return;

      current = ((index % slides.length) + slides.length) % slides.length;
      for (var i = 0; i < slides.length; i++) {
        slides[i].classList.toggle('active', i === current);
      }
      updateDots();
    }

    function next() { show(current + 1); }
    function prev() { show(current - 1); }

    function updateDots() {
      if (!dotsContainer) return;
      var dots = dotsContainer.querySelectorAll('.dot');
      for (var i = 0; i < dots.length; i++) {
        dots[i].classList.toggle('active', i === current);
      }
    }

    function startAuto() {
      if (prefersReducedMotion || paused) return;
      stopAuto();
      timer = setInterval(next, interval);
    }

    function stopAuto() {
      if (timer) { clearInterval(timer); timer = null; }
    }

    // Arrow buttons
    if (prevBtn) prevBtn.addEventListener('click', function () { prev(); startAuto(); });
    if (nextBtn) nextBtn.addEventListener('click', function () { next(); startAuto(); });

    // Dot clicks
    if (dotsContainer) {
      dotsContainer.addEventListener('click', function (e) {
        var dot = e.target.closest('.dot');
        if (!dot) return;
        var idx = parseInt(dot.dataset.index, 10);
        if (!isNaN(idx)) { show(idx); startAuto(); }
      });
    }

    // Pause/play toggle
    if (pauseBtn) {
      pauseBtn.addEventListener('click', function () {
        paused = !paused;
        var icon = pauseBtn.querySelector('.icon');
        if (paused) {
          stopAuto();
          swapIcon(icon, 'icon-pause', 'icon-play');
          pauseBtn.setAttribute('aria-label', pauseBtn.getAttribute('aria-label').replace('Pause', 'Play'));
        } else {
          startAuto();
          swapIcon(icon, 'icon-play', 'icon-pause');
          pauseBtn.setAttribute('aria-label', pauseBtn.getAttribute('aria-label').replace('Play', 'Pause'));
        }
      });
    }

    // Pause on hover
    container.addEventListener('mouseenter', stopAuto);
    container.addEventListener('mouseleave', function () { if (!paused) startAuto(); });

    // Init
    show(0);
    startAuto();

    return { show: show, next: next, prev: prev, refresh: function () { slides = container.querySelectorAll(opts.slideSelector); show(0); startAuto(); } };
  }

  // Initialize reviews carousel
  var reviewCarousel = Carousel('reviews-carousel', {
    slideSelector: '.review-slide',
    dotsId: 'review-dots',
    prevId: 'review-prev',
    nextId: 'review-next',
    pauseId: 'review-pause',
    interval: 6000
  });

  // Expose for dynamic reviews injection
  window.initReviewCarousel = function () {
    reviewCarousel = Carousel('reviews-carousel', {
      slideSelector: '.review-slide',
      dotsId: 'review-dots',
      prevId: 'review-prev',
      nextId: 'review-next',
      pauseId: 'review-pause',
      interval: 6000
    });
  };

  // Initialize specials carousel
  Carousel('specials-carousel', {
    slideSelector: '.specials-slide',
    dotsId: 'specials-dots',
    prevId: 'specials-prev',
    nextId: 'specials-next',
    pauseId: 'specials-pause',
    interval: 5000
  });


  /* ========================================================================
     4. MAP — Click-to-load
     ======================================================================== */

  (function initMap() {
    var mapContainer = document.getElementById('map-container');
    if (!mapContainer) return;

    // onclick is set inline in the HTML template for immediate response.
    // This JS handler is a fallback / progressive enhancement.
    if (!mapContainer.getAttribute('onclick')) {
      mapContainer.addEventListener('click', function () {
        var address = mapContainer.dataset.address || '';
        var title = mapContainer.dataset.title || 'Location map';
        if (!address) return;
        mapContainer.innerHTML = '<iframe title="' + escHtml(title) + '" ' +
          'src="https://www.google.com/maps/embed/v1/place?key=AIzaSyBFw0Qbyq9zTFTd-tUY6dZWTgaQzuU17R8&q=' + encodeURIComponent(address) + '" ' +
          'width="100%" height="100%" style="border:0;min-height:450px;" ' +
          'allowfullscreen="" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe>';
      });
    }
  })();


  /* ========================================================================
     5. REVIEWS WORKER FETCH
     Handled inline in reviews.html <script> block.
     The fetch script runs immediately, calls window.initReviewCarousel()
     after injection. This section is intentionally empty — the logic
     lives in the component template to keep it co-located with the HTML
     it modifies.
     ======================================================================== */


  /* ========================================================================
     6. MODALS
     ======================================================================== */

  (function initModals() {
    var openTriggers = document.querySelectorAll('[data-modal]');
    var lastFocused = null;

    for (var i = 0; i < openTriggers.length; i++) {
      openTriggers[i].addEventListener('click', function (e) {
        e.preventDefault();
        var modalId = this.dataset.modal;
        var modal = document.getElementById(modalId);
        if (!modal) return;

        lastFocused = document.activeElement;
        openModal(modal);

        // Contact modal: pre-select type if data-contact-type is set
        var contactType = this.dataset.contactType;
        if (contactType) {
          var radio = modal.querySelector('input[value="' + contactType + '"]');
          if (radio) {
            radio.checked = true;
            radio.dispatchEvent(new Event('change', { bubbles: true }));
          }
        }
      });
    }

    // Close buttons
    var closeBtns = document.querySelectorAll('.modal-close');
    for (var j = 0; j < closeBtns.length; j++) {
      closeBtns[j].addEventListener('click', function () {
        var modal = this.closest('.modal-overlay');
        if (modal) closeModal(modal);
      });
    }

    // Close on overlay click
    var overlays = document.querySelectorAll('.modal-overlay');
    for (var k = 0; k < overlays.length; k++) {
      overlays[k].addEventListener('click', function (e) {
        if (e.target === this) closeModal(this);
      });
    }

    // Close on ESC
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var openModal = document.querySelector('.modal-overlay.open');
        if (openModal) closeModal(openModal);
      }
    });

    function openModal(modal) {
      modal.classList.add('open');
      modal.style.display = 'flex';
      document.body.style.overflow = 'hidden';
      trapFocus(modal);
    }

    function closeModal(modal) {
      modal.classList.remove('open');
      modal.style.display = 'none';
      document.body.style.overflow = '';
      if (lastFocused) lastFocused.focus();
    }

    // Contact modal — radio group switches form panels
    var contactRadios = document.querySelectorAll('#contact-type-group input[type="radio"]');
    for (var m = 0; m < contactRadios.length; m++) {
      contactRadios[m].addEventListener('change', function () {
        var panels = document.querySelectorAll('.contact-form-panel');
        for (var p = 0; p < panels.length; p++) {
          panels[p].classList.toggle('active', panels[p].dataset.type === this.value);
        }
      });
    }
  })();


  /* ========================================================================
     7. ACCESSIBILITY
     ======================================================================== */

  // Focus trap for modals
  function trapFocus(modal) {
    var focusable = modal.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;

    var first = focusable[0];
    var last = focusable[focusable.length - 1];

    first.focus();

    modal.addEventListener('keydown', function handler(e) {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }

      // Clean up when modal closes
      if (!modal.classList.contains('open')) {
        modal.removeEventListener('keydown', handler);
      }
    });
  }

  // Gallery lightbox (if present)
  (function initLightbox() {
    var items = document.querySelectorAll('[data-lightbox]');
    if (!items.length) return;

    // Create lightbox overlay
    var lightbox = document.createElement('div');
    lightbox.className = 'gallery-lightbox';
    lightbox.innerHTML = '<button class="gallery-lightbox-close" aria-label="Close lightbox">&times;</button><img src="" alt="">';
    document.body.appendChild(lightbox);

    var lbImg = lightbox.querySelector('img');
    var lbClose = lightbox.querySelector('.gallery-lightbox-close');

    for (var i = 0; i < items.length; i++) {
      items[i].addEventListener('click', function (e) {
        e.preventDefault();
        lbImg.src = this.href;
        lbImg.alt = this.dataset.alt || '';
        lightbox.classList.add('open');
        document.body.style.overflow = 'hidden';
      });
    }

    lbClose.addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', function (e) {
      if (e.target === lightbox) closeLightbox();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && lightbox.classList.contains('open')) closeLightbox();
    });

    function closeLightbox() {
      lightbox.classList.remove('open');
      document.body.style.overflow = '';
      lbImg.src = '';
    }
  })();


  /* ========================================================================
     UTILITIES
     ======================================================================== */

  function swapIcon(el, fromClass, toClass) {
    if (!el) return;
    el.classList.remove(fromClass);
    el.classList.add(toClass);
  }

  function escHtml(str) {
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(str));
    return d.innerHTML;
  }

});
