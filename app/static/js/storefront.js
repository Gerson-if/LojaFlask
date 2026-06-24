(() => {
  const toast = document.querySelector("[data-store-toast]");
  const body = document.body;

  const showToast = (message, isError = false) => {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("is-error", isError);
    toast.classList.add("is-visible");
    window.clearTimeout(showToast.timeout);
    showToast.timeout = window.setTimeout(() => toast.classList.remove("is-visible"), 2200);
  };

  const updateCartCount = (count) => {
    document.querySelectorAll("[data-cart-count]").forEach((element) => {
      element.textContent = count;
    });
  };

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-qty-step]");
    if (!button) return;
    const control = button.closest(".quantity-control");
    const input = control?.querySelector("[data-qty-input]");
    if (!input) return;

    const step = Number(button.dataset.qtyStep || 0);
    const min = Number(input.min || 0);
    const max = Number(input.max || 999999);
    const current = Number(input.value || min);
    input.value = Math.max(min, Math.min(max, current + step));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });

  document.querySelectorAll(".js-add-to-cart").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("button[type='submit'], button:not([type])");
      button?.setAttribute("disabled", "disabled");

      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
          },
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || "Não foi possível adicionar.");
        }
        updateCartCount(payload.cart_count);
        showToast(payload.message || "Produto adicionado ao carrinho.");
      } catch (error) {
        showToast(error.message || "Não foi possível adicionar.", true);
      } finally {
        button?.removeAttribute("disabled");
      }
    });
  });

  const sidebar = document.querySelector("[data-category-drawer]");
  const sidebarToggleButtons = document.querySelectorAll("[data-category-toggle]");
  const sidebarCloseButtons = document.querySelectorAll("[data-category-close]");
  const sidebarStorageKey = "storefront-sidebar-collapsed";
  const isMobile = () => window.matchMedia("(max-width: 900px)").matches;

  const syncSidebar = () => {
    if (!sidebar) return;
    if (isMobile()) {
      body.classList.remove("store-sidebar-collapsed");
      body.classList.remove("store-sidebar-open");
      return;
    }
    if (localStorage.getItem(sidebarStorageKey) === "1") {
      body.classList.add("store-sidebar-collapsed");
    } else {
      body.classList.remove("store-sidebar-collapsed");
    }
  };

  const closeMobileSidebar = () => body.classList.remove("store-sidebar-open");

  sidebarToggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (!sidebar) return;
      if (isMobile()) {
        body.classList.toggle("store-sidebar-open");
        return;
      }
      body.classList.toggle("store-sidebar-collapsed");
      localStorage.setItem(
        sidebarStorageKey,
        body.classList.contains("store-sidebar-collapsed") ? "1" : "0"
      );
    });
  });

  sidebarCloseButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (isMobile()) {
        closeMobileSidebar();
        return;
      }
      body.classList.toggle("store-sidebar-collapsed");
      localStorage.setItem(
        sidebarStorageKey,
        body.classList.contains("store-sidebar-collapsed") ? "1" : "0"
      );
    });
  });

  sidebar?.addEventListener("click", (event) => {
    if (isMobile() && event.target.closest("a")) {
      closeMobileSidebar();
    }
  });

  window.addEventListener("resize", syncSidebar);
  syncSidebar();

  document.querySelectorAll("[data-carousel]").forEach((carousel) => {
    const slides = Array.from(
      carousel.querySelectorAll(".store-hero-slide, .product-gallery-slide")
    );
    const dots = Array.from(carousel.querySelectorAll("[data-carousel-dot]"));
    if (slides.length <= 1) return;

    let index = Math.max(0, slides.findIndex((slide) => slide.classList.contains("is-active")));
    let timer = null;

    const show = (nextIndex) => {
      index = (nextIndex + slides.length) % slides.length;
      slides.forEach((slide, slideIndex) => {
        slide.classList.toggle("is-active", slideIndex === index);
      });
      dots.forEach((dot, dotIndex) => {
        dot.classList.toggle("is-active", dotIndex === index);
      });
    };

    const start = () => {
      timer = window.setInterval(() => show(index + 1), 4500);
    };
    const stop = () => window.clearInterval(timer);

    carousel.querySelector("[data-carousel-prev]")?.addEventListener("click", () => show(index - 1));
    carousel.querySelector("[data-carousel-next]")?.addEventListener("click", () => show(index + 1));
    dots.forEach((dot) => {
      dot.addEventListener("click", () => show(Number(dot.dataset.carouselDot || 0)));
    });
    carousel.addEventListener("mouseenter", stop);
    carousel.addEventListener("mouseleave", start);
    start();
  });
})();
