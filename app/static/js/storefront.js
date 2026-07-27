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
      element.textContent = count > 0 ? String(count) : "";
      const badgeHolder = element.closest(".store-cart-icon, .cart-button");
      if (badgeHolder) {
        badgeHolder.removeAttribute("data-bump");
        // Reflow para garantir que a animação reinicie mesmo em cliques seguidos.
        void badgeHolder.offsetWidth;
        badgeHolder.setAttribute("data-bump", "1");
      }
    });
  };

  // Handler genérico de incremento/decremento para qualquer ".quantity-control"
  // fora do carrinho (ex.: seletor de quantidade na página de produto, antes
  // de adicionar ao carrinho). Dentro do carrinho (`[data-cart-root]`), o
  // próprio handler do carrinho (mais abaixo) já cuida de tudo — incluindo
  // aplicar o incremento/decremento — para evitar dois handlers de clique
  // disputando a mesma quantidade fora de ordem (o handler do carrinho está
  // em um elemento mais interno e dispararia ANTES deste, na fase de bubble,
  // lendo o valor antigo e enviando uma atualização sempre um clique atrasada).
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-qty-step]");
    if (!button) return;
    if (button.closest("[data-cart-root]")) return;
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

  const openSidebar = () => body.classList.add("store-sidebar-open");
  const closeSidebar = () => body.classList.remove("store-sidebar-open");

  sidebarToggleButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (!sidebar) return;
      body.classList.toggle("store-sidebar-open");
    });
  });

  sidebarCloseButtons.forEach((button) => {
    button.addEventListener("click", closeSidebar);
  });

  sidebar?.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeSidebar();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebar();
  });

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

  /* ── Carrinho dinâmico (tela /carrinho) ── */
  const cartRoot = document.querySelector("[data-cart-root]");
  if (cartRoot) {
    const updateUrl = cartRoot.dataset.updateUrl;
    const syncNote = document.querySelector("[data-cart-sync-note]");
    const totalEl = document.querySelector("[data-cart-total]");
    const continueShoppingLink = document.querySelector(".page-heading .btn-outline-lf");
    const storeUrl = continueShoppingLink ? continueShoppingLink.getAttribute("href") : "#";
    const emptyStateMarkup = `
      <div class="card-lf empty-state" data-cart-empty-state>
        <i class="bi bi-cart-x" style="font-size: 2.5rem; display: block; margin-bottom: .75rem; color: #cbd5e1;"></i>
        Seu carrinho está vazio.
        <br><br>
        <a class="btn-primary-lf" href="${storeUrl}">Ver produtos</a>
      </div>`;

    const simpleBRL = (value) => `R$ ${value.toFixed(2)}`;

    const setSyncNote = (state, message) => {
      if (!syncNote) return;
      syncNote.classList.remove("is-saving", "is-error");
      if (state) syncNote.classList.add(state);
      syncNote.textContent = message || "";
    };

    const recomputeRowSubtotal = (item) => {
      const input = item.querySelector("[data-qty-input]");
      const subtotalEl = item.querySelector("[data-cart-subtotal]");
      const unitPrice = Number(item.dataset.unitPrice || 0);
      const qty = Number(input?.value || 0);
      if (subtotalEl) subtotalEl.textContent = simpleBRL(unitPrice * qty);
      return unitPrice * qty;
    };

    const recomputeTotal = () => {
      let total = 0;
      cartRoot.querySelectorAll("[data-cart-item]").forEach((item) => {
        total += recomputeRowSubtotal(item);
      });
      if (totalEl) totalEl.textContent = simpleBRL(total);
      return total;
    };

    const removeItemFromDom = (item) => {
      item.classList.add("is-removing");
      window.setTimeout(() => {
        item.remove();
        recomputeTotal();
        if (!cartRoot.querySelectorAll("[data-cart-item]").length) {
          cartRoot.outerHTML = emptyStateMarkup;
        }
      }, 180);
    };

    let pendingTimer = null;
    const sendUpdate = (item, { remove = false } = {}) => {
      const productId = item.dataset.productId;
      const variantId = item.dataset.variantId || "";
      const input = item.querySelector("[data-qty-input]");
      const quantity = remove ? 0 : Math.max(0, Number(input?.value || 0));

      window.clearTimeout(pendingTimer);
      item.classList.add("is-updating");
      setSyncNote("is-saving", "Atualizando carrinho...");

      pendingTimer = window.setTimeout(async () => {
        try {
          const response = await fetch(updateUrl, {
            method: "POST",
            headers: {
              "Content-Type": "application/x-www-form-urlencoded",
              "Accept": "application/json",
              "X-Requested-With": "XMLHttpRequest",
            },
            body: new URLSearchParams({ product_id: productId, variant_id: variantId, quantity: String(quantity) }),
          });
          const payload = await response.json();
          if (!response.ok || !payload.ok) {
            throw new Error(payload.message || "Não foi possível atualizar o carrinho.");
          }

          updateCartCount(payload.cart_count);

          if (quantity <= 0) {
            removeItemFromDom(item);
          } else {
            if (typeof payload.line_quantity === "number" && input) {
              input.value = payload.line_quantity;
            }
            recomputeTotal();
          }
          if (typeof payload.total === "number" && totalEl) {
            totalEl.textContent = simpleBRL(payload.total);
          }
          setSyncNote(null, "Carrinho atualizado");
          window.setTimeout(() => setSyncNote(null, ""), 1500);
        } catch (error) {
          setSyncNote("is-error", error.message || "Não foi possível atualizar o carrinho.");
        } finally {
          item.classList.remove("is-updating");
        }
      }, 450);
    };

    cartRoot.addEventListener("click", (event) => {
      const removeBtn = event.target.closest("[data-cart-remove]");
      if (removeBtn) {
        const item = removeBtn.closest("[data-cart-item]");
        if (item) sendUpdate(item, { remove: true });
        return;
      }
      const stepBtn = event.target.closest("[data-qty-step]");
      if (stepBtn) {
        const item = stepBtn.closest("[data-cart-item]");
        if (!item) return;
        const input = item.querySelector("[data-qty-input]");
        if (!input) return;

        const step = Number(stepBtn.dataset.qtyStep || 0);
        const min = Number(input.min || 0);
        const max = Number(input.max || 999999);
        const current = Number(input.value || min);
        input.value = Math.max(min, Math.min(max, current + step));

        const plusBtn = item.querySelector('[data-qty-step="1"]');
        if (plusBtn) plusBtn.toggleAttribute("disabled", Number(input.value) >= max);
        recomputeRowSubtotal(item);
        recomputeTotal();
        sendUpdate(item);
      }
    });

    cartRoot.addEventListener("input", (event) => {
      const input = event.target.closest("[data-qty-input]");
      if (!input) return;
      const item = input.closest("[data-cart-item]");
      if (!item) return;
      recomputeRowSubtotal(item);
      recomputeTotal();
      sendUpdate(item);
    });
  }

  /* ── Checkout em duas etapas ── */
  const checkoutForm = document.querySelector("[data-checkout-form]");
  if (checkoutForm) {
    const stepper = document.querySelector("[data-checkout-stepper]");
    const panels = Array.from(checkoutForm.querySelectorAll("[data-step-panel]"));
    const stepIndicators = stepper ? Array.from(stepper.querySelectorAll(".step")) : [];

    const goToStep = (stepNumber) => {
      panels.forEach((panel) => {
        panel.classList.toggle("is-active", panel.dataset.stepPanel === String(stepNumber));
      });
      stepIndicators.forEach((indicator) => {
        const indicatorStep = Number(indicator.dataset.step);
        indicator.classList.toggle("is-active", indicatorStep === stepNumber);
        indicator.classList.toggle("is-done", indicatorStep < stepNumber);
      });
      const activePanel = checkoutForm.querySelector(`[data-step-panel="${stepNumber}"]`);
      activePanel?.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    checkoutForm.querySelectorAll("[data-checkout-next]").forEach((button) => {
      button.addEventListener("click", () => {
        const currentPanel = button.closest("[data-step-panel]");
        const requiredFields = currentPanel ? Array.from(currentPanel.querySelectorAll("[required]")) : [];
        const invalidField = requiredFields.find((field) => !field.checkValidity());
        if (invalidField) {
          invalidField.reportValidity();
          return;
        }
        goToStep(2);
      });
    });

    checkoutForm.querySelectorAll("[data-checkout-back]").forEach((button) => {
      button.addEventListener("click", () => goToStep(1));
    });

    checkoutForm.addEventListener("submit", (event) => {
      const step2Panel = checkoutForm.querySelector('[data-step-panel="2"]');
      if (!step2Panel || !step2Panel.classList.contains("is-active")) {
        event.preventDefault();
        goToStep(2);
        return;
      }
      // O form usa novalidate para controlar manualmente quando a validação
      // do navegador aparece (não queremos validar a etapa 2 enquanto o
      // usuário ainda está na etapa 1). Aqui, na submissão real, validamos
      // todos os campos obrigatórios do formulário inteiro.
      const allRequiredFields = Array.from(checkoutForm.querySelectorAll("[required]"));
      const invalidField = allRequiredFields.find((field) => !field.checkValidity());
      if (invalidField) {
        event.preventDefault();
        const invalidPanel = invalidField.closest("[data-step-panel]");
        if (invalidPanel && invalidPanel.dataset.stepPanel !== "2") {
          goToStep(Number(invalidPanel.dataset.stepPanel));
        }
        window.setTimeout(() => invalidField.reportValidity(), 50);
      }
    });
  }
})();
