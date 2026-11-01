// BT SN Portal - Frontend Logic

let registeredProducts = [];
let registeredGtins = [];
let registeredLines = [];
let currentProductFormMode = "ADD"; // "ADD" or "EDIT"
let currentProductFormId = "";
let currentGtinFormMode = "ADD"; // "ADD" or "EDIT"
let currentGtinFormId = "";

// Image base64 caching
let productBase64Image = "";

function safeAddListener(id, event, handler) {
    const el = document.getElementById(id);
    if (el) {
        el.addEventListener(event, handler);
    }
}

// ==========================================================================
// 21 CFR PART 11 AUTHENTICATION, RBAC & SESSION GOVERNANCE
// ==========================================================================
const AUTH_TOKEN_KEY = "bt_sn_auth_token";
const AUTH_USER_KEY = "bt_sn_auth_user";

function getAuthToken() {
    return localStorage.getItem(AUTH_TOKEN_KEY) || sessionStorage.getItem(AUTH_TOKEN_KEY);
}

function getAuthUser() {
    try {
        const u = localStorage.getItem(AUTH_USER_KEY) || sessionStorage.getItem(AUTH_USER_KEY);
        return u ? JSON.parse(u) : null;
    } catch {
        return null;
    }
}

function setAuthSession(token, user, rememberMe = true) {
    clearAuthSession();
    const storage = rememberMe ? localStorage : sessionStorage;
    storage.setItem(AUTH_TOKEN_KEY, token);
    storage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

function clearAuthSession() {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(AUTH_USER_KEY);
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
    sessionStorage.removeItem(AUTH_USER_KEY);
}

function isAuthenticated() {
    return !!getAuthToken();
}

// Global fetch interceptor ensuring all API requests include 21 CFR Part 11 Bearer credentials
const originalFetch = window.fetch;
window.fetch = async function (url, options = {}) {
    const token = getAuthToken();
    if (token) {
        options = options || {};
        options.headers = options.headers || {};
        if (options.headers instanceof Headers) {
            if (!options.headers.has("Authorization")) {
                options.headers.set("Authorization", `Bearer ${token}`);
            }
        } else if (Array.isArray(options.headers)) {
            options.headers.push(["Authorization", `Bearer ${token}`]);
        } else {
            if (!options.headers["Authorization"]) {
                options.headers["Authorization"] = `Bearer ${token}`;
            }
        }
    }
    const res = await originalFetch(url, options);
    if (res.status === 401 && typeof url === "string" && !url.includes("/api/v1/auth/login") && !url.includes("/api/v1/auth/demo-users")) {
        if (token) {
            clearAuthSession();
            updateAuthUI();
            showAuthOverlay();
            setAuthError("Session has expired or credentials were invalidated. Please sign in again.");
        }
    }
    return res;
};

function hasPermission(moduleKey, actionKey = "view") {
    const user = getAuthUser();
    if (!user) return false;
    const roleStr = (user.role || "").toLowerCase();
    if (user.username === "admin" || roleStr.includes("administrator") || roleStr.includes("lead")) {
        return true;
    }
    const perms = user.permissions || {};
    const modActions = perms[moduleKey] || [];
    return modActions.includes(actionKey);
}

window.hasPermission = hasPermission;

function filterNavigationByPermissions() {
    const user = getAuthUser();
    if (!user) return;

    // Navigation dropdown toggles
    const productsDropdown = document.querySelector("#sub-add-product")?.closest(".portal-nav-dropdown");
    if (productsDropdown) {
        productsDropdown.style.display = hasPermission("products", "view") ? "" : "none";
    }
    const linesDropdown = document.querySelector("#sub-add-line")?.closest(".portal-nav-dropdown");
    if (linesDropdown) {
        linesDropdown.style.display = hasPermission("lines", "view") ? "" : "none";
    }
    const batchesDropdown = document.querySelector("#sub-add-batch")?.closest(".portal-nav-dropdown");
    if (batchesDropdown) {
        batchesDropdown.style.display = hasPermission("batches", "view") ? "" : "none";
    }
    const reportsDropdown = document.querySelector("#sub-audit-logs")?.closest(".portal-nav-dropdown");
    if (reportsDropdown) {
        reportsDropdown.style.display = hasPermission("reports", "view") || hasPermission("audit_logs", "view") ? "" : "none";
    }
    const verifBtn = document.querySelector('.portal-nav-btn[data-view="view-verification"]');
    if (verifBtn) {
        verifBtn.style.display = hasPermission("verification", "view") ? "" : "none";
    }
    const sgtinBtn = document.querySelector('.portal-nav-btn[data-view="view-sgtin"]');
    if (sgtinBtn) {
        sgtinBtn.style.display = hasPermission("sgtin", "view") ? "" : "none";
    }

    // Sub-items based on specific action permissions
    const subAddProd = document.getElementById("sub-add-product");
    if (subAddProd) subAddProd.style.display = hasPermission("products", "create") ? "" : "none";

    const subAddGtin = document.getElementById("sub-add-gtin");
    if (subAddGtin) subAddGtin.style.display = hasPermission("gtin_store", "create") ? "" : "none";

    const subImportSn = document.getElementById("sub-import-sn");
    if (subImportSn) subImportSn.style.display = hasPermission("code_pool", "import") ? "" : "none";

    const subAddLine = document.getElementById("sub-add-line");
    if (subAddLine) subAddLine.style.display = hasPermission("lines", "create") ? "" : "none";

    const subAddBatch = document.getElementById("sub-add-batch");
    if (subAddBatch) subAddBatch.style.display = hasPermission("batches", "create") ? "" : "none";
}

function showAuthOverlay() {
    const overlay = document.getElementById("auth-overlay");
    if (overlay) {
        overlay.classList.remove("hidden");
        overlay.style.display = "flex";
        const errBanner = document.getElementById("auth-error-banner");
        if (errBanner) errBanner.classList.add("hidden");
        const uInput = document.getElementById("login-username");
        if (uInput) setTimeout(() => uInput.focus(), 150);
    }
}

function hideAuthOverlay() {
    const overlay = document.getElementById("auth-overlay");
    if (overlay) {
        overlay.classList.add("hidden");
        overlay.style.display = "none";
    }
}

window.showAuthOverlay = showAuthOverlay;
window.hideAuthOverlay = hideAuthOverlay;
window.isAuthenticated = isAuthenticated;
window.getAuthToken = getAuthToken;
window.getAuthUser = getAuthUser;

function setAuthError(msg) {
    const errBanner = document.getElementById("auth-error-banner");
    const errText = document.getElementById("auth-error-text");
    if (errBanner && errText) {
        errText.textContent = msg || "Authentication failed. Access rejected.";
        errBanner.classList.remove("hidden");
    }
}

function updateAuthUI() {
    const user = getAuthUser();
    const wrapper = document.getElementById("auth-header-wrapper");
    const adminTab = document.getElementById("nav-btn-users");
    const rolesTab = document.getElementById("nav-btn-roles");

    if (user && isAuthenticated()) {
        const initials = (user.full_name || user.username || "U")
            .split(" ")
            .filter(Boolean)
            .slice(0, 2)
            .map(w => w[0].toUpperCase())
            .join("");

        if (wrapper) {
            wrapper.innerHTML = `
                <div class="user-session-badge" title="Authenticated session for ${escapeHtml(user.email || user.username)}">
                    <div class="user-avatar-circle">${escapeHtml(initials)}</div>
                    <div class="user-session-info">
                        <span class="user-session-name">${escapeHtml(user.full_name || user.username)}</span>
                        <div class="user-session-sub">
                            <span class="user-session-role">${escapeHtml(user.role || 'Operator')}</span>
                            <span class="user-session-plant">${escapeHtml(user.plant || 'TESTPLANT')}</span>
                        </div>
                    </div>
                    <button type="button" class="btn-user-signout" id="btn-header-logout" title="Sign out of serialization portal">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
                        <span>Sign Out</span>
                    </button>
                </div>
            `;
            const logoutBtn = document.getElementById("btn-header-logout");
            if (logoutBtn) logoutBtn.addEventListener("click", handleLogout);
        }

        if (adminTab) {
            adminTab.style.display = hasPermission("user_management", "view") ? "inline-flex" : "none";
        }
        if (rolesTab) {
            rolesTab.style.display = hasPermission("roles", "view") ? "inline-flex" : "none";
        }

        filterNavigationByPermissions();

        if (user.require_password_change) {
            showMandatoryPwdChangeModal();
        }
    } else {
        if (wrapper) {
            wrapper.innerHTML = `
                <button type="button" class="btn-nav-signin" id="btn-header-login">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
                    <span>Sign In</span>
                </button>
            `;
            const loginBtn = document.getElementById("btn-header-login");
            if (loginBtn) loginBtn.addEventListener("click", showAuthOverlay);
        }
        if (adminTab) adminTab.style.display = "none";
        if (rolesTab) rolesTab.style.display = "none";
    }
}

async function verifySession() {
    const token = getAuthToken();
    if (!token) {
        updateAuthUI();
        return false;
    }
    try {
        const res = await fetch("/api/v1/auth/me");
        if (res.ok) {
            const user = await res.json();
            try {
                const pRes = await fetch("/api/v1/auth/me/permissions");
                if (pRes.ok) {
                    const pData = await pRes.json();
                    user.permissions = pData.permissions || {};
                    user.require_password_change = pData.require_password_change || false;
                }
            } catch (e) {
                console.warn("Could not refresh permissions:", e);
            }
            setAuthSession(token, user, true);
            updateAuthUI();
            return true;
        } else {
            clearAuthSession();
            updateAuthUI();
            return false;
        }
    } catch (err) {
        console.warn("Session verification network issue:", err);
        if (getAuthUser()) {
            updateAuthUI();
            return true;
        }
        clearAuthSession();
        updateAuthUI();
        return false;
    }
}

async function handleLoginSubmit(e) {
    if (e) e.preventDefault();
    const uInput = document.getElementById("login-username");
    const pInput = document.getElementById("login-password");
    const rememberBox = document.getElementById("login-remember");
    const spinner = document.getElementById("login-spinner");
    const btnText = document.getElementById("login-btn-text");
    const submitBtn = document.getElementById("btn-submit-login");

    const identifier = uInput ? uInput.value.trim() : "";
    const password = pInput ? pInput.value : "";
    const rememberMe = rememberBox ? rememberBox.checked : true;

    if (!identifier || !password) {
        setAuthError("Please provide both User ID and password.");
        return;
    }

    if (spinner) spinner.classList.remove("hidden");
    if (btnText) btnText.textContent = "Verifying Credentials...";
    if (submitBtn) submitBtn.disabled = true;

    try {
        const res = await fetch("/api/v1/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                username_or_email: identifier,
                password: password,
                remember_me: rememberMe
            })
        });

        if (res.ok) {
            const data = await res.json();
            const userObj = data.user || {};
            userObj.permissions = data.permissions || {};
            userObj.require_password_change = data.require_password_change || false;
            setAuthSession(data.access_token || data.token, userObj, rememberMe);
            hideAuthOverlay();
            updateAuthUI();

            if (pInput) pInput.value = "";

            if (userObj.require_password_change) {
                showMandatoryPwdChangeModal();
            } else {
                const serSection = document.getElementById("serialization");
                if (serSection) {
                    serSection.scrollIntoView({ behavior: "smooth" });
                }
            }
        } else {
            const err = await res.json().catch(() => ({}));
            setAuthError(err.detail || "Invalid User ID or password. Electronic access rejected.");
        }
    } catch (err) {
        console.error("Login request failed:", err);
        setAuthError("Unable to reach authorization server. Please verify network status.");
    } finally {
        if (spinner) spinner.classList.add("hidden");
        if (btnText) btnText.textContent = "Sign In";
        if (submitBtn) submitBtn.disabled = false;
    }
}

function showMandatoryPwdChangeModal() {
    const modal = document.getElementById("modal-mandatory-pwd-change");
    if (modal) {
        modal.classList.remove("hidden");
        modal.style.display = "flex";
    }
}

window.showMandatoryPwdChangeModal = showMandatoryPwdChangeModal;

async function handleMandatoryPwdChange() {
    const oldP = document.getElementById("change-old-password")?.value;
    const newP = document.getElementById("change-new-password")?.value;
    const confP = document.getElementById("change-confirm-password")?.value;
    const errBanner = document.getElementById("pwd-change-error-banner");
    const errText = document.getElementById("pwd-change-error-text");

    if (!oldP || !newP || !confP) {
        if (errBanner && errText) {
            errText.textContent = "Please fill in all mandatory fields.";
            errBanner.classList.remove("hidden");
        }
        return;
    }
    if (newP !== confP) {
        if (errBanner && errText) {
            errText.textContent = "New passwords do not match. Please re-enter.";
            errBanner.classList.remove("hidden");
        }
        return;
    }
    if (newP.length < 8) {
        if (errBanner && errText) {
            errText.textContent = "New password must be at least 8 characters with upper, lower, digit & special char.";
            errBanner.classList.remove("hidden");
        }
        return;
    }

    try {
        const res = await fetch("/api/v1/auth/change-password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ old_password: oldP, new_password: newP })
        });
        if (res.ok) {
            const user = getAuthUser();
            if (user) {
                user.require_password_change = false;
                setAuthSession(getAuthToken(), user, true);
            }
            const modal = document.getElementById("modal-mandatory-pwd-change");
            if (modal) {
                modal.classList.add("hidden");
                modal.style.display = "none";
            }
            alert("Password updated successfully! Welcome to BharatTraq.");
        } else {
            const err = await res.json().catch(() => ({}));
            if (errBanner && errText) {
                errText.textContent = err.detail || "Failed to update password.";
                errBanner.classList.remove("hidden");
            }
        }
    } catch (e) {
        if (errBanner && errText) {
            errText.textContent = "Network error: " + e.message;
            errBanner.classList.remove("hidden");
        }
    }
}

window.handleLoginSubmit = handleLoginSubmit;
window.handleLogout = handleLogout;

async function handleLogout() {
    const token = getAuthToken();
    if (token) {
        try {
            await fetch("/api/v1/auth/logout", {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` }
            });
        } catch (e) {
            console.warn("Logout notification failed:", e);
        }
    }
    clearAuthSession();
    updateAuthUI();
    showAuthOverlay();
}

// ----------------- Password Visibility Toggle -----------------
let lastPwdToggleTimestamp = 0;
window.togglePasswordVisibility = function (e) {
    if (e) {
        if (typeof e.preventDefault === 'function') e.preventDefault();
        if (typeof e.stopPropagation === 'function') e.stopPropagation();
        if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();
    }
    const now = Date.now();
    if (now - lastPwdToggleTimestamp < 120) {
        return; // debounce against accidental double triggers
    }
    lastPwdToggleTimestamp = now;

    const pInput = document.getElementById("login-password");
    const eyeBtn = document.getElementById("btn-toggle-pwd");
    if (!pInput) return;

    const isPwd = (pInput.type === "password" || pInput.getAttribute("type") === "password");
    if (isPwd) {
        pInput.type = "text";
        pInput.setAttribute("type", "text");
        if (eyeBtn) {
            eyeBtn.setAttribute("title", "Hide password");
            eyeBtn.setAttribute("aria-label", "Hide password");
            eyeBtn.innerHTML = `<svg id="pwd-eye-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="pointer-events: none;"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`;
        }
    } else {
        pInput.type = "password";
        pInput.setAttribute("type", "password");
        if (eyeBtn) {
            eyeBtn.setAttribute("title", "Show password");
            eyeBtn.setAttribute("aria-label", "Show password");
            eyeBtn.innerHTML = `<svg id="pwd-eye-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="pointer-events: none;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
        }
    }
    try {
        pInput.focus();
    } catch (_) {}
};

function setupAuthListeners() {
    safeAddListener("login-form", "submit", handleLoginSubmit);
    safeAddListener("btn-submit-login", "click", handleLoginSubmit);

    // Password visibility toggle
    safeAddListener("btn-toggle-pwd", "click", (e) => {
        window.togglePasswordVisibility(e);
    });

    // Quick Fill Admin credentials
    safeAddListener("quick-fill-admin", "click", () => {
        const u = document.getElementById("login-username");
        const p = document.getElementById("login-password");
        if (u) u.value = "admin";
        if (p) p.value = "Admin@1234";
        const errBanner = document.getElementById("auth-error-banner");
        if (errBanner) errBanner.classList.add("hidden");
    });

    // Quick Fill Operator credentials
    safeAddListener("quick-fill-operator", "click", () => {
        const u = document.getElementById("login-username");
        const p = document.getElementById("login-password");
        if (u) u.value = "operator";
        if (p) p.value = "Operator@1234";
        const errBanner = document.getElementById("auth-error-banner");
        if (errBanner) errBanner.classList.add("hidden");
    });

    // Browse Documentation Dismiss
    safeAddListener("btn-browse-docs", "click", () => {
        hideAuthOverlay();
        const topEl = document.getElementById("top");
        if (topEl) topEl.scrollIntoView({ behavior: "smooth" });
    });

    // Top Header Sign In button
    safeAddListener("btn-header-login", "click", showAuthOverlay);

    // Prompt login on console navigation if unauthenticated
    const consoleLinks = ["nav-open-portal"];
    consoleLinks.forEach(id => {
        safeAddListener(id, "click", (e) => {
            if (!isAuthenticated()) {
                e.preventDefault();
                showAuthOverlay();
            }
        });
    });
}

// ----------------- Admin User Management & RBAC Governance -----------------
let allRolesList = [];
let availableModulesMetadata = {};
let currentSelectedRoleId = null;

async function loadUsersTable() {
    const tbody = document.getElementById("users-table-body");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted">Retrieving authorized users from directory...</td></tr>`;

    try {
        const res = await fetch("/api/v1/auth/users");
        if (!res.ok) throw new Error("Failed to load user directory");
        const users = await res.json();

        if (users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted">No users found in database.</td></tr>`;
            return;
        }

        tbody.innerHTML = users.map(u => {
            const roleBadge = u.role.includes("Lead") || u.role.includes("Administrator")
                ? `<span class="role-badge role-badge-admin">${escapeHtml(u.role)}</span>`
                : `<span class="role-badge role-badge-user">${escapeHtml(u.role)}</span>`;
            
            const statusBadge = u.is_active
                ? `<span class="status-pill status-active">Active</span>`
                : `<span class="status-pill status-disabled">Disabled</span>`;

            const pwdChangeBadge = u.require_password_change
                ? `<span class="status-pill status-pending">Pending</span>`
                : `<span class="status-pill status-complete">Set</span>`;

            const lastLoginFmt = u.last_login ? new Date(u.last_login).toLocaleString() : "Never";

            return `
                <tr>
                    <td class="cell-id">#${u.id}</td>
                    <td class="cell-mono">${escapeHtml(u.username)}</td>
                    <td class="cell-name">${escapeHtml(u.full_name)}</td>
                    <td>${roleBadge}</td>
                    <td><span class="user-session-plant">${escapeHtml(u.plant || 'TESTPLANT')}</span></td>
                    <td><a href="mailto:${escapeHtml(u.email)}" class="user-email-link">${escapeHtml(u.email)}</a></td>
                    <td>${statusBadge}</td>
                    <td>${pwdChangeBadge}</td>
                    <td><span class="cell-muted">${escapeHtml(lastLoginFmt)}</span></td>
                    <td>
                        <button type="button" class="btn-action-small ${u.is_active ? 'btn-deact' : 'btn-act'}" onclick="toggleUserStatus(${u.id}, ${u.is_active})">
                            ${u.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                        <button type="button" class="btn-action-small" onclick="openAdminResetPwdModal(${u.id}, '${escapeHtml(u.username)}')">
                            Reset Pwd
                        </button>
                        <button type="button" class="btn-action-small" onclick="openUserOverridesModal(${u.id}, '${escapeHtml(u.username)}', '${escapeHtml(u.role)}')">
                            Overrides
                        </button>
                    </td>
                </tr>
            `;
        }).join("");
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger">Error loading users: ${escapeHtml(err.message)}</td></tr>`;
    }
}

async function toggleUserStatus(userId, isCurrentlyActive) {
    const actionName = isCurrentlyActive ? "deactivate" : "activate";
    const msg = isCurrentlyActive 
        ? "Are you sure you want to deactivate this account? All active workstation sessions will be terminated immediately."
        : "Reactivate this account and permit system login?";
    if (!confirm(msg)) return;

    try {
        const res = await fetch(`/api/v1/auth/users/${userId}/status`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_active: !isCurrentlyActive })
        });
        if (res.ok) {
            loadUsersTable();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || `Failed to ${actionName} user account.`);
        }
    } catch (e) {
        alert("Network error: " + e.message);
    }
}

function openAdminResetPwdModal(userId, username) {
    const modal = document.getElementById("admin-reset-pwd-modal");
    const targetIdEl = document.getElementById("reset-target-user-id");
    const targetUserEl = document.getElementById("reset-target-username");
    const newPwdInput = document.getElementById("reset-new-password");
    const reqChangeBox = document.getElementById("reset-require-change");

    if (targetIdEl) targetIdEl.value = userId;
    if (targetUserEl) targetUserEl.textContent = username;
    if (newPwdInput) newPwdInput.value = "";
    if (reqChangeBox) reqChangeBox.checked = true;

    if (modal) modal.classList.remove("hidden");
}

async function submitAdminResetPassword() {
    const userId = document.getElementById("reset-target-user-id")?.value;
    const newPwd = document.getElementById("reset-new-password")?.value;
    const reqChange = document.getElementById("reset-require-change")?.checked ?? true;

    if (!userId || !newPwd || newPwd.length < 8) {
        alert("Please enter a password of at least 8 characters (including upper, lower, digit & special char).");
        return;
    }

    try {
        const res = await fetch(`/api/v1/auth/users/${userId}/reset-password`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                new_password: newPwd,
                require_password_change: reqChange
            })
        });

        if (res.ok) {
            const modal = document.getElementById("admin-reset-pwd-modal");
            if (modal) modal.classList.add("hidden");
            loadUsersTable();
            alert("Temporary password has been set. User must update password upon next login.");
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || "Failed to reset password.");
        }
    } catch (e) {
        alert("Network error: " + e.message);
    }
}

async function openUserOverridesModal(userId, username, roleName) {
    const modal = document.getElementById("user-overrides-modal");
    const targetIdEl = document.getElementById("override-target-user-id");
    const targetUserEl = document.getElementById("override-target-username");
    const targetRoleEl = document.getElementById("override-target-role");
    const tbody = document.getElementById("user-overrides-table-body");

    if (targetIdEl) targetIdEl.value = userId;
    if (targetUserEl) targetUserEl.textContent = username;
    if (targetRoleEl) targetRoleEl.textContent = roleName;
    if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Loading permissions...</td></tr>`;

    if (modal) modal.classList.remove("hidden");

    try {
        // Fetch permissions matrix metadata
        if (Object.keys(availableModulesMetadata).length === 0) {
            const metaRes = await fetch("/api/v1/auth/permissions-matrix");
            if (metaRes.ok) availableModulesMetadata = await metaRes.json();
        }

        const mods = Object.keys(availableModulesMetadata);
        let rows = [];

        mods.forEach(modKey => {
            const meta = availableModulesMetadata[modKey] || {};
            const actions = meta.actions || [];
            actions.forEach(act => {
                const displayAct = act.replace(/_/g, ' ');
                rows.push(`
                    <tr>
                        <td class="col-module-cell"><span class="module-title">${escapeHtml(meta.name || modKey)}</span></td>
                        <td><span class="action-chip">${escapeHtml(displayAct)}</span></td>
                        <td><span class="cell-muted">Role Default</span></td>
                        <td><span class="cell-muted" id="override-status-${escapeHtml(modKey)}-${escapeHtml(act)}">Inherited</span></td>
                        <td>
                            <button type="button" class="btn-action-small btn-act" onclick="setUserOverride(${userId}, '${escapeHtml(modKey)}', '${escapeHtml(act)}', true)">Grant</button>
                            <button type="button" class="btn-action-small btn-deact" onclick="setUserOverride(${userId}, '${escapeHtml(modKey)}', '${escapeHtml(act)}', false)">Deny</button>
                        </td>
                    </tr>
                `);
            });
        });

        if (tbody) tbody.innerHTML = rows.join("");
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="5" class="text-danger">Failed to load override matrix: ${escapeHtml(e.message)}</td></tr>`;
    }
}

async function setUserOverride(userId, moduleKey, actionKey, isAllowed) {
    try {
        const res = await fetch(`/api/v1/auth/users/${userId}/permissions`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                module_key: moduleKey,
                action_key: actionKey,
                is_allowed: isAllowed
            })
        });
        if (res.ok) {
            const statusEl = document.getElementById(`override-status-${moduleKey}-${actionKey}`);
            if (statusEl) {
                statusEl.innerHTML = isAllowed 
                    ? `<span style="color:#0b663b; font-weight:700;">Granted</span>`
                    : `<span style="color:#b31d1d; font-weight:700;">Denied</span>`;
            }
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || "Failed to set permission override.");
        }
    } catch (e) {
        alert("Network error: " + e.message);
    }
}

// ----------------- Roles & Privileges (RBAC) -----------------
async function loadRolesView() {
    try {
        const [rolesRes, metaRes] = await Promise.all([
            fetch("/api/v1/auth/roles"),
            fetch("/api/v1/auth/permissions-matrix")
        ]);
        if (rolesRes.ok) {
            allRolesList = await rolesRes.json();
        }
        if (metaRes.ok) {
            availableModulesMetadata = await metaRes.json();
        }
        renderRolesPillBar();
        populateRoleDropdownInUserModal();
        if (allRolesList.length > 0) {
            if (!currentSelectedRoleId || !allRolesList.some(r => r.id === currentSelectedRoleId)) {
                currentSelectedRoleId = allRolesList[0].id;
            }
            selectRole(currentSelectedRoleId);
        }
    } catch (e) {
        console.error("Error loading roles view:", e);
    }
}

function renderRolesPillBar() {
    const container = document.getElementById("roles-pill-container");
    if (!container) return;
    container.innerHTML = allRolesList.map(r => {
        const activeClass = r.id === currentSelectedRoleId ? "active" : "";
        const sysTag = r.is_system_role ? `<span class="role-sys-tag">System</span>` : "";
        return `
            <button type="button" class="role-pill-btn ${activeClass}" onclick="selectRole(${r.id})">
                <span>${escapeHtml(r.role_name)}</span>
                ${sysTag}
            </button>
        `;
    }).join("");
}

function selectRole(roleId) {
    currentSelectedRoleId = roleId;
    renderRolesPillBar();
    const role = allRolesList.find(r => r.id === roleId);
    if (!role) return;

    const titleEl = document.getElementById("current-role-title");
    const descEl = document.getElementById("current-role-desc");
    const badgeEl = document.getElementById("current-role-system-badge");
    const delBtn = document.getElementById("btn-delete-role");

    if (titleEl) titleEl.textContent = role.role_name;
    if (descEl) descEl.textContent = role.description || "No description provided.";
    if (badgeEl) {
        if (role.is_system_role) {
            badgeEl.textContent = "System Template";
            badgeEl.className = "role-status-tag role-status-system";
        } else {
            badgeEl.textContent = "Custom Role";
            badgeEl.className = "role-status-tag role-status-custom";
        }
    }
    if (delBtn) {
        delBtn.style.display = role.is_system_role ? "none" : "inline-flex";
    }

    renderRolePermissionsTable(role);
}

function renderRolePermissionsTable(role) {
    const tbody = document.getElementById("role-permissions-table-body");
    if (!tbody) return;

    const rolePerms = role.permissions || {};
    const modules = Object.keys(availableModulesMetadata);

    if (modules.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" class="text-center text-muted">No modules registered.</td></tr>`;
        return;
    }

    tbody.innerHTML = modules.map(modKey => {
        const meta = availableModulesMetadata[modKey] || {};
        const modName = meta.name || modKey;
        const modDesc = meta.description || "";
        const modActions = meta.actions || [];
        const grantedActions = rolePerms[modKey] || [];
        const isSystemAdmin = role.role_name === "System Administrator";

        const actionCheckboxes = modActions.map(act => {
            const isChecked = grantedActions.includes(act);
            const displayLabel = act.replace(/_/g, ' ');
            return `
                <label class="action-checkbox-item ${isChecked ? 'checked' : ''} ${isSystemAdmin ? 'is-disabled' : ''}">
                    <input type="checkbox" data-module="${escapeHtml(modKey)}" data-action="${escapeHtml(act)}" ${isChecked ? 'checked' : ''} ${isSystemAdmin ? 'disabled' : ''} onchange="this.parentElement.classList.toggle('checked', this.checked)">
                    <span class="action-label">${escapeHtml(displayLabel)}</span>
                </label>
            `;
        }).join("");

        return `
            <tr>
                <td class="col-module-cell">
                    <span class="module-title">${escapeHtml(modName)}</span>
                </td>
                <td class="col-desc-cell">
                    <span class="module-desc">${escapeHtml(modDesc)}</span>
                </td>
                <td class="col-actions-cell">
                    <div class="action-checkbox-grid">${actionCheckboxes}</div>
                </td>
            </tr>
        `;
    }).join("");
}

async function saveCurrentRolePermissions() {
    const role = allRolesList.find(r => r.id === currentSelectedRoleId);
    if (!role) return;

    if (role.role_name === "System Administrator") {
        alert("System Administrator permissions are immutable to ensure compliance with 21 CFR Part 11.");
        return;
    }

    const tbody = document.getElementById("role-permissions-table-body");
    if (!tbody) return;

    const newPerms = {};
    tbody.querySelectorAll("input[type='checkbox']").forEach(cb => {
        if (cb.checked) {
            const mod = cb.getAttribute("data-module");
            const act = cb.getAttribute("data-action");
            if (!newPerms[mod]) newPerms[mod] = [];
            newPerms[mod].push(act);
        }
    });

    try {
        const res = await fetch(`/api/v1/auth/roles/${role.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                description: role.description,
                permissions: newPerms
            })
        });
        if (res.ok) {
            const updated = await res.json();
            const idx = allRolesList.findIndex(r => r.id === role.id);
            if (idx !== -1) allRolesList[idx] = updated;
            selectRole(role.id);
            alert(`Permissions matrix for "${role.role_name}" updated and committed to audit trail!`);
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || "Failed to update role permissions.");
        }
    } catch (e) {
        alert("Error saving role permissions: " + e.message);
    }
}

function openCreateRoleModal() {
    const modal = document.getElementById("create-role-modal");
    const nameInput = document.getElementById("new-role-name");
    const descInput = document.getElementById("new-role-desc");
    const tbody = document.getElementById("new-role-perms-body");

    if (nameInput) nameInput.value = "";
    if (descInput) descInput.value = "";

    if (tbody) {
        const modules = Object.keys(availableModulesMetadata);
        tbody.innerHTML = modules.map(modKey => {
            const meta = availableModulesMetadata[modKey] || {};
            const actions = meta.actions || [];
            const checkboxes = actions.map(act => {
                const displayLabel = act.replace(/_/g, ' ');
                return `
                    <label class="action-checkbox-item">
                        <input type="checkbox" data-module="${escapeHtml(modKey)}" data-action="${escapeHtml(act)}" onchange="this.parentElement.classList.toggle('checked', this.checked)">
                        <span class="action-label">${escapeHtml(displayLabel)}</span>
                    </label>
                `;
            }).join("");

            return `
                <tr>
                    <td class="col-module-cell"><span class="module-title">${escapeHtml(meta.name || modKey)}</span></td>
                    <td class="col-actions-cell"><div class="action-checkbox-grid">${checkboxes}</div></td>
                </tr>
            `;
        }).join("");
    }

    if (modal) modal.classList.remove("hidden");
}

async function submitCreateRole() {
    const nameInput = document.getElementById("new-role-name");
    const descInput = document.getElementById("new-role-desc");
    const roleName = nameInput ? nameInput.value.trim() : "";
    const roleDesc = descInput ? descInput.value.trim() : "";

    if (!roleName) {
        alert("Please enter a role name.");
        return;
    }

    const tbody = document.getElementById("new-role-perms-body");
    const perms = {};
    if (tbody) {
        tbody.querySelectorAll("input[type='checkbox']").forEach(cb => {
            if (cb.checked) {
                const mod = cb.getAttribute("data-module");
                const act = cb.getAttribute("data-action");
                if (!perms[mod]) perms[mod] = [];
                perms[mod].push(act);
            }
        });
    }

    try {
        const res = await fetch("/api/v1/auth/roles", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                role_name: roleName,
                description: roleDesc,
                permissions: perms
            })
        });

        if (res.ok) {
            const newRole = await res.json();
            const modal = document.getElementById("create-role-modal");
            if (modal) modal.classList.add("hidden");
            await loadRolesView();
            selectRole(newRole.id);
            alert(`Custom Role "${newRole.role_name}" provisioned successfully!`);
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || "Failed to create custom role.");
        }
    } catch (e) {
        alert("Network error: " + e.message);
    }
}

async function deleteCurrentRole() {
    const role = allRolesList.find(r => r.id === currentSelectedRoleId);
    if (!role) return;
    if (role.is_system_role) {
        alert("System Roles are permanent and protected under 21 CFR Part 11.");
        return;
    }

    if (!confirm(`Are you sure you want to permanently delete custom role "${role.role_name}"?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/v1/auth/roles/${role.id}`, {
            method: "DELETE"
        });
        if (res.ok) {
            currentSelectedRoleId = null;
            await loadRolesView();
            alert(`Role "${role.role_name}" has been removed.`);
        } else {
            const err = await res.json().catch(() => ({}));
            alert(err.detail || "Failed to delete role.");
        }
    } catch (e) {
        alert("Network error: " + e.message);
    }
}

function populateRoleDropdownInUserModal() {
    const select = document.getElementById("new-user-role");
    if (!select || allRolesList.length === 0) return;
    select.innerHTML = allRolesList.map(r => `
        <option value="${escapeHtml(r.role_name)}" data-role-id="${r.id}">${escapeHtml(r.role_name)} ${r.is_system_role ? '(Standard)' : '(Custom)'}</option>
    `).join("");
}

window.toggleUserStatus = toggleUserStatus;
window.openAdminResetPwdModal = openAdminResetPwdModal;
window.submitAdminResetPassword = submitAdminResetPassword;
window.openUserOverridesModal = openUserOverridesModal;
window.setUserOverride = setUserOverride;
window.selectRole = selectRole;
window.saveCurrentRolePermissions = saveCurrentRolePermissions;
window.openCreateRoleModal = openCreateRoleModal;
window.submitCreateRole = submitCreateRole;
window.deleteCurrentRole = deleteCurrentRole;

function setupUserManagement() {
    safeAddListener("btn-open-create-user-modal", "click", () => {
        const modal = document.getElementById("create-user-modal");
        const errBanner = document.getElementById("create-user-error-banner");
        if (errBanner) errBanner.classList.add("hidden");
        populateRoleDropdownInUserModal();
        if (modal) modal.classList.remove("hidden");
    });

    safeAddListener("btn-close-create-user-modal", "click", () => {
        const modal = document.getElementById("create-user-modal");
        if (modal) modal.classList.add("hidden");
    });

    safeAddListener("create-user-form", "submit", handleCreateUserSubmit);
    safeAddListener("btn-submit-create-user", "click", handleCreateUserSubmit);

    // Reset password modal
    safeAddListener("btn-close-admin-reset-modal", "click", () => {
        const m = document.getElementById("admin-reset-pwd-modal");
        if (m) m.classList.add("hidden");
    });
    safeAddListener("btn-submit-admin-reset-pwd", "click", submitAdminResetPassword);

    // Overrides modal
    safeAddListener("btn-close-overrides-modal", "click", () => {
        const m = document.getElementById("user-overrides-modal");
        if (m) m.classList.add("hidden");
    });

    // Roles & Privileges
    safeAddListener("btn-save-role-permissions", "click", saveCurrentRolePermissions);
    safeAddListener("btn-open-create-role-modal", "click", openCreateRoleModal);
    safeAddListener("btn-close-create-role-modal", "click", () => {
        const m = document.getElementById("create-role-modal");
        if (m) m.classList.add("hidden");
    });
    safeAddListener("btn-submit-create-role", "click", submitCreateRole);
    safeAddListener("btn-delete-role", "click", deleteCurrentRole);

    // Mandatory Password Change submit
    safeAddListener("btn-submit-pwd-change", "click", handleMandatoryPwdChange);
}

async function handleCreateUserSubmit(e) {
    if (e) e.preventDefault();
    const fullName = document.getElementById("new-user-fullname")?.value.trim();
    const username = document.getElementById("new-user-username")?.value.trim();
    const email = document.getElementById("new-user-email")?.value.trim();
    const roleSelect = document.getElementById("new-user-role");
    const role = roleSelect ? roleSelect.value : "";
    const selectedOption = roleSelect ? roleSelect.options[roleSelect.selectedIndex] : null;
    const roleId = selectedOption ? parseInt(selectedOption.getAttribute("data-role-id") || "0") : null;
    const plant = document.getElementById("new-user-plant")?.value;
    const password = document.getElementById("new-user-password")?.value;
    const reqChange = document.getElementById("new-user-require-pwd-change")?.checked ?? true;
    const errBanner = document.getElementById("create-user-error-banner");
    const errText = document.getElementById("create-user-error-text");

    if (!fullName || !username || !email || !password) {
        if (errBanner && errText) {
            errText.textContent = "Please complete all mandatory fields.";
            errBanner.classList.remove("hidden");
        }
        return;
    }

    try {
        const res = await fetch("/api/v1/auth/users", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                full_name: fullName,
                username: username,
                email: email,
                role: role,
                role_id: roleId || undefined,
                plant: plant,
                password: password,
                require_password_change: reqChange
            })
        });

        if (res.ok) {
            const newUser = await res.json();
            const modal = document.getElementById("create-user-modal");
            if (modal) modal.classList.add("hidden");
            
            document.getElementById("create-user-form")?.reset();
            loadUsersTable();
            alert(`Authorized user account "${newUser.username}" (${newUser.full_name}) created successfully!`);
        } else {
            const err = await res.json().catch(() => ({}));
            if (errBanner && errText) {
                errText.textContent = err.detail || "Failed to provision user.";
                errBanner.classList.remove("hidden");
            }
        }
    } catch (err) {
        if (errBanner && errText) {
            errText.textContent = err.message || "Network error while creating user.";
            errBanner.classList.remove("hidden");
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

function initApp() {
    checkSystemHealth();
    setInterval(checkSystemHealth, 10000);
    
    // Auth & Identity Governance
    setupAuthListeners();
    setupUserManagement();
    verifySession();

    // Setup routing and UI controls immediately
    setupRouting();
    setupDropdownToggles();
    setupProductDropdownListeners();
    setupSerialTypeHandlers();
    setupStatusToggleListeners();
    setupEventListeners();
    setupFileHandlers();
    
    // Initial data loading
    loadAllData();
    
    // Set initial batch idempotency keys
    generateNewBatchIdempotencyKey();

    // Prompt login screen if not authenticated
    if (!isAuthenticated()) {
        showAuthOverlay();
    }
}

function setupDropdownToggles() {
    // Close all dropdowns helper
    function closeAllDropdowns() {
        document.querySelectorAll(".portal-nav-dropdown-content").forEach(c => {
            c.classList.remove("show-dropdown");
        });
    }

    // Toggle buttons (parent dropdown labels) — only open/close the dropdown
    document.querySelectorAll(".portal-nav-toggle").forEach(toggleBtn => {
        toggleBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            const content = toggleBtn.nextElementSibling;
            if (!content) return;
            const isOpen = content.classList.contains("show-dropdown");
            closeAllDropdowns();
            if (!isOpen) {
                content.classList.add("show-dropdown");
            }
        });
    });

    // Close dropdowns when clicking anywhere outside the nav
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".portal-nav-dropdown")) {
            closeAllDropdowns();
        }
    });
}

// ----------------- Routing & Tab Switching -----------------
function setupRouting() {
    // Direct nav buttons (no dropdown)
    document.querySelectorAll(".portal-nav-btn[data-view]").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            switchView(btn.getAttribute("data-view"));
        });
    });

    // Sub-menu buttons inside dropdowns
    document.querySelectorAll(".portal-nav-sub-btn[data-view]").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            // Close all dropdowns
            document.querySelectorAll(".portal-nav-dropdown-content").forEach(c => {
                c.classList.remove("show-dropdown");
            });

            const viewId = btn.getAttribute("data-view");
            // Reset forms when navigating to add views
            if (btn.id === "sub-add-product") resetProductForm();
            if (btn.id === "sub-add-gtin")    resetGtinForm();
            if (btn.id === "sub-add-batch")   resetBatchForm();
            if (btn.id === "sub-add-line")    resetLineForm();
            if (btn.id === "sub-add-io")      populateIoForm();

            switchView(viewId);
        });
    });
}

function convertDateInputToApiExpiry(dateString) {
    if (!dateString) return "";
    const clean = dateString.trim();
    if (/^\d{6}$/.test(clean)) return clean;
    if (clean.includes("-")) {
        const parts = clean.split("-");
        if (parts.length === 3) {
            if (parts[0].length === 4) return parts[0].slice(2) + parts[1].padStart(2, "0") + parts[2].padStart(2, "0");
            if (parts[2].length === 4) return parts[2].slice(2) + parts[1].padStart(2, "0") + parts[0].padStart(2, "0");
        }
    }
    if (clean.includes("/")) {
        const parts = clean.split("/");
        if (parts.length === 3) {
            if (parts[2].length === 4) return parts[2].slice(2) + parts[1].padStart(2, "0") + parts[0].padStart(2, "0");
            if (parts[0].length === 4) return parts[0].slice(2) + parts[1].padStart(2, "0") + parts[2].padStart(2, "0");
        }
    }
    return clean;
}

function convertApiExpiryToDateInput(val) {
    if (!/^\d{6}$/.test(val || "")) return "";
    return `20${val.slice(0, 2)}-${val.slice(2, 4)}-${val.slice(4, 6)}`;
}

function convertDateInputToMfgDisplay(dateString) {
    if (!dateString) return "";
    const clean = dateString.trim();
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(clean)) return clean;
    if (clean.includes("-")) {
        const parts = clean.split("-");
        if (parts.length === 3) {
            if (parts[0].length === 4) return `${parts[2].padStart(2, "0")}/${parts[1].padStart(2, "0")}/${parts[0]}`;
            if (parts[2].length === 4) return `${parts[0].padStart(2, "0")}/${parts[1].padStart(2, "0")}/${parts[2]}`;
        }
    }
    if (clean.includes("/")) {
        const parts = clean.split("/");
        if (parts.length === 3) {
            if (parts[2].length === 4) return `${parts[0].padStart(2, "0")}/${parts[1].padStart(2, "0")}/${parts[2]}`;
        }
    }
    return clean;
}

function convertMfgDisplayToDateInput(val) {
    if (!/^\d{2}\/\d{2}\/\d{4}$/.test(val || "")) return "";
    const parts = val.split("/");
    return `${parts[2]}-${parts[1]}-${parts[0]}`;
}

function loadAllData() {
    loadProducts();
    loadGtins();
    loadBatches();
    loadAuditLogs();
    loadLines();
}

async function loadAllCounts() {
    const prodCount = document.getElementById("dash-prod-count");
    const gtinCount = document.getElementById("dash-gtin-count");
    const batchCount = document.getElementById("dash-batch-count");

    if (prodCount) prodCount.textContent = registeredProducts.length;
    if (gtinCount) gtinCount.textContent = registeredGtins.length;
    
    try {
        const res = await fetch("/api/v1/serialization/batches");
        if (res.ok) {
            const data = await res.json();
            if (batchCount) batchCount.textContent = data.length;
        }
    } catch (e) {
        console.error("Failed to load batch count for dashboard.", e);
    }
}

// ----------------- Core Data Loaders -----------------
async function loadProducts() {
    try {
        const res = await fetch("/api/v1/products");
        if (res.ok) {
            registeredProducts = await res.json();
            renderProductList(registeredProducts);
            loadAllCounts();
            populateProductDropdowns();
        }
    } catch (e) {
        console.error("Failed to load products", e);
    }
}

async function loadGtins() {
    try {
        const res = await fetch("/api/v1/gtin-store");
        if (res.ok) {
            registeredGtins = await res.json();
            renderGtinList(registeredGtins);
            loadAllCounts();
        }
    } catch (e) {
        console.error("Failed to load GTIN store", e);
    }
}

async function loadBatches() {
    try {
        const res = await fetch("/api/v1/serialization/batches");
        if (res.ok) {
            const batches = await res.json();
            renderBatchList(batches);
            loadAllCounts();
        }
    } catch (e) {
        console.error("Failed to load batches", e);
    }
}

async function loadAuditLogs() {
    try {
        const res = await fetch("/api/v1/audit-logs");
        if (res.ok) {
            const logs = await res.json();
            renderAuditLogs(logs);
        }
    } catch (e) {
        console.error("Failed to load audit logs", e);
    }
}

async function loadLines() {
    try {
        const res = await fetch("/api/v1/lines");
        if (res.ok) {
            registeredLines = await res.json();
            populateLineDropdown();
            renderLineList(registeredLines);
            populateIoLineDropdown();
        }
    } catch (e) {
        console.error("Failed to load packaging lines", e);
    }
}

function populateLineDropdown() {
    const sel = document.getElementById("batch-line");
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = `<option value="" disabled selected>-- Select Packaging Line --</option>`;
    registeredLines.forEach(l => {
        const opt = document.createElement("option");
        opt.value = l.line_id;
        const lineName = l.name || l.line_name || l.line_id;
        const proto = l.io_protocol || l.protocol || "DIRECT_API";
        opt.textContent = `${lineName} (${l.line_id}) - ${proto}`;
        sel.appendChild(opt);
    });
    if (currentVal) sel.value = currentVal;
}

function updateRecipeCalculation() {
    const qtyInput = document.getElementById("batch-qty");
    const secRatioInput = document.getElementById("batch-ratio-sec");
    const terRatioInput = document.getElementById("batch-ratio-ter");
    const prodIdInput = document.getElementById("batch-product-id");

    const priEl = document.getElementById("calc-pri-qty");
    const secEl = document.getElementById("calc-sec-qty");
    const terEl = document.getElementById("calc-ter-qty");
    const totalEl = document.getElementById("calc-total-qty");
    const zeroNote = document.getElementById("recipe-zero-limit-note");

    if (!qtyInput) return;

    const qPri = Math.max(parseInt(qtyInput.value || 0, 10), 0);
    const rSec = Math.max(parseInt(secRatioInput ? secRatioInput.value : 10, 10) || 1, 1);
    const rTer = Math.max(parseInt(terRatioInput ? terRatioInput.value : 10, 10) || 1, 1);

    let qSec = qPri > 0 ? Math.ceil(qPri / rSec) : 0;
    let qTer = qSec > 0 ? Math.ceil(qSec / rTer) : 0;

    let zeroLimitHit = false;
    const productId = prodIdInput ? prodIdInput.value : "";
    if (productId && registeredGtins && registeredGtins.length > 0) {
        const productGtins = registeredGtins.filter(g => g.product_id === productId);
        productGtins.forEach(g => {
            const level = (g.packaging_level || "").toLowerCase();
            if (g.limit === 0) {
                zeroLimitHit = true;
                if (level.includes("sec")) qSec = 0;
                if (level.includes("ter")) qTer = 0;
            }
        });
    }

    if (priEl) priEl.textContent = qPri;
    if (secEl) secEl.textContent = qSec;
    if (terEl) terEl.textContent = qTer;
    if (totalEl) totalEl.textContent = (qPri + qSec + qTer);
    if (zeroNote) {
        if (zeroLimitHit) zeroNote.classList.remove("hidden");
        else zeroNote.classList.add("hidden");
    }
}

// ----------------- Data Renderers -----------------
function renderProductList(products) {
    const tbody = document.getElementById("prod-list-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (products.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center">No products found.</td></tr>`;
        return;
    }

    products.forEach(p => {
        const tr = document.createElement("tr");
        const statusClass = p.is_active ? "badge-success" : "badge-secondary";
        const statusText = p.is_active ? "Activated" : "Inactive";
        
        tr.innerHTML = `
            <td>${p.manufacturer || "N/A"}</td>
            <td>${p.plant || "N/A"}</td>
            <td><strong>${p.product_id}</strong></td>
            <td>${p.name}</td>
            <td>${p.marketing_level || "N/A"}</td>
            <td><span class="badge ${statusClass}">${statusText}</span></td>
            <td>
                <button class="btn secondary-btn btn-sm" onclick="editProduct('${p.product_id}')">Edit</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function renderGtinList(gtins) {
    const tbody = document.getElementById("gtin-list-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (gtins.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" class="text-center">No GTIN mapping records found.</td></tr>`;
        return;
    }

    gtins.forEach(g => {
        const tr = document.createElement("tr");
        const statusText = g.enable_gtin ? "Activated" : "Inactive";
        const statusClass = g.enable_gtin ? "badge-success" : "badge-secondary";
        
        // Find product name
        const prod = registeredProducts.find(p => p.product_id === g.product_id);
        const prodName = prod ? prod.name : g.product_id;

        const isSscc = (g.serial_no_type === "SSCC");
        const typeBadgeClass = isSscc ? "badge-warning" : "badge-info";

        tr.innerHTML = `
            <td>${g.manufacturer}</td>
            <td>${g.plant}</td>
            <td>${prodName}</td>
            <td><strong>${g.product_code}</strong></td>
            <td>${g.packaging_level}</td>
            <td>${g.packing_size}</td>
            <td><code>${g.gtin}</code></td>
            <td>
                <span class="badge ${typeBadgeClass}" style="font-weight: 600; font-size: 0.78rem;">${g.serial_no_type || "SGTIN"}</span>
                <small class="text-muted" style="display:block; font-size: 0.72rem; margin-top: 2px;">${g.packaging_category || ""}</small>
            </td>
            <td>${g.limit}</td>
            <td>${g.case_quantity !== null ? g.case_quantity : "N/A"}</td>
            <td><span class="badge ${statusClass}">${statusText}</span></td>
            <td>
                <button class="btn secondary-btn btn-sm" onclick="window.editGtin(${g.id})">Edit</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function renderBatchList(batches) {
    const tbody = document.getElementById("batches-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (batches.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center">No batch generations found.</td></tr>`;
        return;
    }

    batches.forEach(b => {
        const tr = document.createElement("tr");
        
        let statusClass = "badge-secondary";
        let statusLabel = b.status || "UNKNOWN";
        if (b.status === "COMPLETED") { statusClass = "badge-success"; }
        else if (b.status === "LOADED") { statusClass = "badge-info"; }
        else if (b.status === "STARTED") { statusClass = "badge-warning"; }
        else if (b.status === "RECONCILED") { statusClass = "badge-primary"; }
        else if (b.status === "CLOSED") { statusClass = "badge-dark"; statusLabel = "🔒 CLOSED"; }
        else if (b.status === "FAILED") { statusClass = "badge-danger"; }

        const seqRange = (b.start_sequence && b.end_sequence) ? `${b.start_sequence} - ${b.end_sequence}` : "N/A";
        
        let actionButtons = [];
        
        // Phase 2: Load
        if (b.status === "COMPLETED" || b.status === "CREATED") {
            actionButtons.push(`<button class="btn primary-btn btn-sm" onclick="window.loadBatch('${b.batch_id}')" style="margin-right:4px;" title="Phase 2: Dispatch batch to Level 2 Line">Load</button>`);
        }
        // Phase 3: Start
        else if (b.status === "LOADED") {
            actionButtons.push(`<button class="btn primary-btn btn-sm" onclick="window.startBatch('${b.batch_id}')" style="margin-right:4px;" title="Phase 3: Trigger start on Level 2 Line">Start</button>`);
        }
        // Phase 3: Reconcile
        else if (b.status === "STARTED") {
            const totalSerials = b.generated_quantity || b.requested_quantity || 0;
            actionButtons.push(`<button class="btn primary-btn btn-sm" onclick="window.openReconcileModal('${b.batch_id}', ${totalSerials})" style="margin-right:4px;" title="Phase 3: Submit Good/Rejected/Unused counts">Reconcile</button>`);
        }
        // Phase 4: Close
        else if (b.status === "RECONCILED") {
            actionButtons.push(`<button class="btn primary-btn btn-sm" onclick="window.closeBatch('${b.batch_id}')" style="margin-right:4px;" title="Phase 4: Close and lock batch">Close</button>`);
        }

        // Compliance Reports
        if (b.status === "RECONCILED" || b.status === "CLOSED" || b.reconciled_good_count !== null) {
            actionButtons.push(`<button class="btn secondary-btn btn-sm" onclick="window.downloadXmlReport('${b.batch_id}')" style="margin-right:4px;" title="Export GS1 EPCIS XML compliance report">XML</button>`);
            actionButtons.push(`<button class="btn secondary-btn btn-sm" onclick="window.showBatchSummary('${b.batch_id}')" style="margin-right:4px;" title="View Batch Summary and Metrics">Summary</button>`);
        }

        // Always allow Verify
        actionButtons.push(`<button class="btn secondary-btn btn-sm" onclick="window.verifyDirectSerial('${b.batch_id}')">Verify</button>`);

        tr.innerHTML = `
            <td><strong>${b.batch_id}</strong></td>
            <td>${b.product_id}</td>
            <td>${b.requested_quantity}</td>
            <td>${b.generated_quantity}</td>
            <td><code>${seqRange}</code></td>
            <td>${b.batch_lot}</td>
            <td>${formatExpiryForDisplay(b.expiry_date)}</td>
            <td><span class="badge ${statusClass}">${statusLabel}</span></td>
            <td><span class="badge ${b.aggregated_batch ? 'badge-info' : 'badge-secondary'}">${b.aggregated_batch ? 'Yes' : 'No'}</span></td>
            <td>${actionButtons.join(" ")}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderAuditLogs(logs) {
    window.currentAuditLogs = logs || [];
    const tbody = document.getElementById("audit-logs-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (logs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center">No logs recorded.</td></tr>`;
        return;
    }

    logs.forEach(l => {
        const tr = document.createElement("tr");
        const timeStr = new Date(l.timestamp).toLocaleString();
        
        tr.innerHTML = `
            <td><small class="text-muted">${timeStr}</small></td>
            <td><span class="badge badge-info">${l.event_type}</span></td>
            <td><code>${l.table_name}</code></td>
            <td><strong>${l.record_id}</strong></td>
            <td><code>${l.performed_by}</code></td>
            <td>
                <button class="btn secondary-btn btn-sm" onclick="viewAuditDetails(${l.id}, '${escapeHtml(l.previous_value || '')}', '${escapeHtml(l.updated_value || '')}')">Details</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

const VIEW_MODULE_MAP = {
    "view-dashboard": "dashboard",
    "view-product-add": "products",
    "view-product-list": "products",
    "view-gtin-add": "gtin_store",
    "view-gtin-list": "gtin_store",
    "view-sn-import": "code_pool",
    "view-line-add": "lines",
    "view-line-io": "lines",
    "view-line-list": "lines",
    "view-batch-add": "batches",
    "view-batch-list": "batches",
    "view-batch-xml": "batches",
    "view-report-summary": "reports",
    "view-report-detail": "reports",
    "view-verification": "verification",
    "view-sgtin": "sgtin",
    "view-audit-logs": "audit_logs",
    "view-users": "user_management",
    "view-roles": "roles"
};

function switchView(viewId) {
    if (!isAuthenticated() && viewId !== "view-dashboard") {
        showAuthOverlay();
        return;
    }

    const modKey = VIEW_MODULE_MAP[viewId];
    if (modKey && modKey !== "dashboard" && !hasPermission(modKey, "view")) {
        alert(`Access Denied: Your account does not have permission to view the ${modKey.toUpperCase()} module.`);
        switchView("view-dashboard");
        return;
    }

    document.querySelectorAll(".portal-view").forEach(view => {
        view.classList.add("hidden");
    });
    
    const target = document.getElementById(viewId);
    if (target) {
        target.classList.remove("hidden");
    }

    // Update active class on nav buttons
    document.querySelectorAll(".portal-nav-btn, .portal-nav-sub-btn").forEach(btn => {
        btn.classList.remove("active");
    });

    const activeBtn = document.querySelector(`.portal-nav-btn[data-view="${viewId}"]`) ||
                      document.querySelector(`.portal-nav-sub-btn[data-view="${viewId}"]`);
    if (activeBtn) {
        activeBtn.classList.add("active");
        
        // highlight parent dropdown if it's a sub-menu button
        const parentDropdown = activeBtn.closest(".portal-nav-dropdown");
        if (parentDropdown) {
            const dropBtn = parentDropdown.querySelector(".portal-nav-btn");
            if (dropBtn) dropBtn.classList.add("active");
        }
    }

    // Auto-refresh data when landing on views
    if (viewId === "view-line-list") {
        loadLines();
    } else if (viewId === "view-line-io") {
        populateIoForm();
    } else if (viewId === "view-sn-import") {
        setupPoolImportView();
        window.loadCodePoolStats();
    } else if (viewId === "view-batch-xml") {
        setupXmlReportView();
    } else if (viewId === "view-report-summary") {
        window.loadBatchSummaryReport();
    } else if (viewId === "view-report-detail") {
        setupBatchReportDetailView();
    } else if (viewId === "view-product-list") {
        loadProducts();
    } else if (viewId === "view-gtin-list") {
        loadGtins();
    } else if (viewId === "view-batch-list") {
        loadBatches();
    } else if (viewId === "view-audit-logs") {
        loadAuditLogs();
    } else if (viewId === "view-users") {
        loadUsersTable();
    } else if (viewId === "view-roles") {
        loadRolesView();
    }
}

window.switchView = switchView;

window.goToAddBatch = function() {
    resetBatchForm();
    switchView("view-batch-add");
};

window.goToAddProduct = function() {
    resetProductForm();
    switchView("view-product-add");
};

window.goToAddGtin = function() {
    resetGtinForm();
    switchView("view-gtin-add");
};

// ----------------- Edit Actions -----------------
window.editProduct = function(productId) {
    const product = registeredProducts.find(p => p.product_id === productId);
    if (!product) return;

    currentProductFormMode = "EDIT";
    currentProductFormId = productId;

    document.getElementById("product-form-title").textContent = `Edit Product: ${productId}`;
    
    // Fill in values
    document.getElementById("prod-regulatory").value = product.regulatory_authority || "";
    document.getElementById("prod-codeprovider").value = product.code_provider || "";
    document.getElementById("prod-manufacturer").value = product.manufacturer || "";
    document.getElementById("prod-plant").value = product.plant || "";
    document.getElementById("prod-marketinglevel").value = product.marketing_level || "";
    
    const prodIdInput = document.getElementById("prod-id");
    prodIdInput.value = product.product_id;
    prodIdInput.readOnly = true;
    prodIdInput.classList.add("readonly-input");

    document.getElementById("prod-name").value = product.name;
    document.getElementById("prod-name2").value = product.product_name_2 || "";
    document.getElementById("prod-name3").value = product.product_name_3 || "";
    document.getElementById("prod-stk").value = product.stk || "";
    document.getElementById("prod-mfgby").value = product.manufactured_by || "";
    document.getElementById("prod-distby").value = product.distributed_by || "";
    document.getElementById("prod-storage").value = product.storage_condition || "";
    document.getElementById("prod-license").value = product.license || "";
    document.getElementById("prod-generic").value = product.generic_name || "";
    document.getElementById("prod-composition").value = product.composition || "";
    document.getElementById("prod-usagedose").value = product.usage_dose || "";
    document.getElementById("prod-remark").value = product.remark || "";
    document.getElementById("prod-price").value = product.unit_price || "";
    document.getElementById("prod-gtin").value = product.gtin;
    
    document.getElementById("prod-ndc").value = product.ndc || "";
    document.getElementById("prod-ndctype").value = product.ndc_type || "";
    document.getElementById("prod-countrycode-type").value = product.country_drug_code_type || "";
    document.getElementById("prod-countrycode").value = product.country_drug_code || "";
    document.getElementById("prod-materialnumber").value = product.internal_material_number || "";
    document.getElementById("prod-nnhrn").value = product.nnhrn || "";
    document.getElementById("prod-nhrnai-type").value = product.nhrn_ai_type || "";
    
    document.getElementById("prod-itemcode-type").value = product.item_code_type || "";
    document.getElementById("prod-itemcode").value = product.item_code || "";
    
    // Toggle active state radio
    const activeRadios = document.getElementsByName("prod-active");
    activeRadios.forEach(radio => {
        radio.checked = (radio.value === "true" && product.is_active) || (radio.value === "false" && !product.is_active);
    });

    document.getElementById("prod-add1").value = product.additional_field_1 || "";
    document.getElementById("prod-add2").value = product.additional_field_2 || "";
    
    // Load image preview
    const preview = document.getElementById("prod-img-preview");
    const previewInfo = document.getElementById("prod-img-size-info");
    if (product.product_image) {
        productBase64Image = product.product_image;
        preview.src = product.product_image;
        preview.classList.remove("hidden");
        previewInfo.textContent = "Existing image loaded.";
    } else {
        productBase64Image = "";
        preview.src = "";
        preview.classList.add("hidden");
        previewInfo.textContent = "";
    }

    // Profile accordion settings
    document.getElementById("prof-len").value = product.profile.length;
    document.getElementById("prof-dups").value = product.profile.allow_duplicate_characters ? "true" : "false";

    // Toggle panels based on authority selection
    toggleAuthorityPanels(product.regulatory_authority);

    switchView("view-product-add");
};

window.editGtin = function(gtinId) {
    const gtin = registeredGtins.find(g => g.id === gtinId || String(g.id) === String(gtinId));
    if (!gtin) {
        console.warn("GTIN record not found for ID:", gtinId);
        return;
    }

    currentGtinFormMode = "EDIT";
    currentGtinFormId = gtin.id;

    const titleEl = document.getElementById("gtin-form-title");
    if (titleEl) titleEl.textContent = `Edit GTIN Mappings`;

    const mfgEl = document.getElementById("gtin-manufacturer");
    if (mfgEl) mfgEl.value = gtin.manufacturer || "";

    const plantEl = document.getElementById("gtin-plant");
    if (plantEl) plantEl.value = gtin.plant || "";

    const pkgLevelEl = document.getElementById("gtin-pkglevel");
    if (pkgLevelEl) pkgLevelEl.value = gtin.packaging_level || "";
    
    // Set product input, select (if any), and hidden ID safely
    const prod = registeredProducts.find(p => p.product_id === gtin.product_id);
    const prodInput = document.getElementById("gtin-product-input");
    if (prodInput) {
        prodInput.value = prod ? `${prod.name} (${prod.product_id})` : gtin.product_id;
    }
    const prodSelect = document.getElementById("gtin-product-select");
    if (prodSelect) prodSelect.value = gtin.product_id;

    const prodIdEl = document.getElementById("gtin-product-id");
    if (prodIdEl) prodIdEl.value = gtin.product_id;
    
    const prodCodeEl = document.getElementById("gtin-productcode");
    if (prodCodeEl) prodCodeEl.value = gtin.product_code || "";

    const pkgSizeEl = document.getElementById("gtin-pkgsize");
    if (pkgSizeEl) pkgSizeEl.value = gtin.packing_size || "";

    const valEl = document.getElementById("gtin-val");
    if (valEl) valEl.value = gtin.gtin || "";
    
    const enabledRadios = document.getElementsByName("gtin-enabled");
    enabledRadios.forEach(radio => {
        radio.checked = (radio.value === "true" && gtin.enable_gtin) || (radio.value === "false" && !gtin.enable_gtin);
    });

    const caseQtyEl = document.getElementById("gtin-caseqty");
    if (caseQtyEl) caseQtyEl.value = (gtin.case_quantity !== null && gtin.case_quantity !== undefined) ? gtin.case_quantity : "";

    const limitEl = document.getElementById("gtin-limit");
    if (limitEl) limitEl.value = (gtin.limit !== null && gtin.limit !== undefined) ? gtin.limit : "";

    const codeLenEl = document.getElementById("gtin-codelen");
    if (codeLenEl) codeLenEl.value = gtin.code_length || 20;

    // Populate Serial No Type and Packaging Category
    const serialTypeRadios = document.getElementsByName("gtin-serial-type");
    serialTypeRadios.forEach(radio => {
        radio.checked = (radio.value === (gtin.serial_no_type || "SGTIN"));
    });
    const pkgCatSelect = document.getElementById("gtin-pkgcategory");
    if (pkgCatSelect) {
        pkgCatSelect.value = gtin.packaging_category || (gtin.serial_no_type === "SSCC" ? "Tertiary" : "Primary");
    }
    const helperContainer = document.getElementById("serial-type-helper");
    const helperText = document.getElementById("serial-type-helper-text");
    if (helperContainer && helperText) {
        if (gtin.serial_no_type === "SSCC") {
            helperContainer.style.background = "#fff8e6";
            helperContainer.style.borderColor = "#fde293";
            helperContainer.style.color = "#7c4a03";
            helperText.innerHTML = `<strong>SSCC Mode Active:</strong> Encodes AI (00) Serial Shipping Container Code for logistics packaging (Tertiary / Pallet).`;
        } else {
            helperContainer.style.background = "#eaf4fe";
            helperContainer.style.borderColor = "#d0e7fc";
            helperContainer.style.color = "#08445f";
            helperText.innerHTML = `<strong>SGTIN Mode Active:</strong> Encodes AI (01) GTIN + AI (21) Serial Number for saleable trade packaging (Primary / Secondary / Inner).`;
        }
    }

    switchView("view-gtin-add");
};

function editGtin(gtinId) {
    window.editGtin(gtinId);
}

window.editBatch = function(batchId) {
    // Load batch details
    alert(`Editing Batch properties for batch ${batchId}. The serial generated counts cannot be altered, but header attributes can be updated.`);
    
    // We fetch batch and load it into Add Batch form
    fetch(`/api/v1/serialization/batches/${batchId}`)
        .then(res => res.json())
        .then(batch => {
            document.getElementById("batch-form-title").textContent = `Edit Batch: ${batch.batch_id}`;
            document.getElementById("batch-manufacturer").value = batch.manufacturer || "";
            document.getElementById("batch-plant").value = batch.plant || "";
            document.getElementById("batch-pkglevel").value = batch.packaging_level || "";
            
            // Set product input, select (if any), and hidden ID safely
            const prod = registeredProducts.find(p => p.product_id === batch.product_id);
            const batchProdInput = document.getElementById("batch-product-input");
            if (batchProdInput) {
                batchProdInput.value = prod ? `${prod.name} (${prod.product_id})` : batch.product_id;
            }
            const batchProdSelect = document.getElementById("batch-product-select");
            if (batchProdSelect) batchProdSelect.value = batch.product_id;
            const batchProdId = document.getElementById("batch-product-id");
            if (batchProdId) batchProdId.value = batch.product_id;
            
            document.getElementById("batch-pkgsize").value = batch.packaging_size || "";
            document.getElementById("batch-workorder").value = batch.work_order_no || "";
            document.getElementById("batch-num").value = batch.batch_lot;
            document.getElementById("batch-gtin").value = batch.gtin;
            document.getElementById("batch-mfgdate").value = convertMfgDisplayToDateInput(batch.mfg_date);
            
            // Format expiry YYMMDD back to display or standard text
            document.getElementById("batch-expiry").value = convertApiExpiryToDateInput(batch.expiry_date);
            
            const enabledRadios = document.getElementsByName("batch-enabled");
            enabledRadios.forEach(radio => {
                radio.checked = (radio.value === "true" && batch.is_enabled) || (radio.value === "false" && !batch.is_enabled);
            });

            const aggBatchRadios = document.getElementsByName("batch-aggregated");
            aggBatchRadios.forEach(radio => {
                radio.checked = (radio.value === "true" && batch.aggregated_batch) || (radio.value === "false" && !batch.aggregated_batch);
            });

            document.getElementById("batch-aggregation").checked = batch.package_aggregation;
            document.getElementById("batch-parentcode").checked = batch.parent_code_required;

            // Hide quantity field group for existing edits
            const qtyEl = document.getElementById("batch-qty");
            if (qtyEl) {
                const grp = qtyEl.closest(".form-group");
                if (grp) grp.classList.add("hidden");
            }
            
            // Store edit keys
            const form = document.getElementById("batch-form");
            if (form) {
                form.dataset.mode = "EDIT";
                form.dataset.batchId = batch.batch_id;
            }

            switchView("view-batch-add");
        });
};

// ----------------- Resets -----------------
function resetProductForm() {
    currentProductFormMode = "ADD";
    currentProductFormId = "";
    const title = document.getElementById("product-form-title");
    if (title) title.textContent = "Add Product";
    const form = document.getElementById("product-form");
    if (form) form.reset();
    
    const prodIdInput = document.getElementById("prod-id");
    if (prodIdInput) {
        prodIdInput.readOnly = false;
        prodIdInput.classList.remove("readonly-input");
    }

    const preview = document.getElementById("prod-img-preview");
    if (preview) preview.classList.add("hidden");
    const previewInfo = document.getElementById("prod-img-size-info");
    if (previewInfo) previewInfo.textContent = "";
    productBase64Image = "";

    const dscsa = document.getElementById("panel-dscsa");
    if (dscsa) dscsa.classList.add("hidden");
    const eufmd = document.getElementById("panel-eufmd");
    if (eufmd) eufmd.classList.add("hidden");
}

function resetGtinForm() {
    currentGtinFormMode = "ADD";
    currentGtinFormId = "";
    const title = document.getElementById("gtin-form-title");
    if (title) title.textContent = "Add GTIN";
    const form = document.getElementById("gtin-form");
    if (form) form.reset();
    const prodId = document.getElementById("gtin-product-id");
    if (prodId) prodId.value = "";
    const prodInput = document.getElementById("gtin-product-input");
    if (prodInput) prodInput.value = "";

    const serialTypeRadios = document.getElementsByName("gtin-serial-type");
    serialTypeRadios.forEach(radio => {
        radio.checked = (radio.value === "SGTIN");
    });
    const pkgCatSelect = document.getElementById("gtin-pkgcategory");
    if (pkgCatSelect) pkgCatSelect.value = "Primary";
    const helperContainer = document.getElementById("serial-type-helper");
    const helperText = document.getElementById("serial-type-helper-text");
    if (helperContainer && helperText) {
        helperContainer.style.background = "#eaf4fe";
        helperContainer.style.borderColor = "#d0e7fc";
        helperContainer.style.color = "#08445f";
        helperText.innerHTML = `<strong>SGTIN Mode Active:</strong> Encodes AI (01) GTIN + AI (21) Serial Number for saleable trade packaging (Primary / Secondary / Inner).`;
    }
}

function resetBatchForm() {
    const title = document.getElementById("batch-form-title");
    if (title) title.textContent = "Add Batch";
    const form = document.getElementById("batch-form");
    if (form) {
        form.reset();
        form.dataset.mode = "ADD";
        form.dataset.batchId = "";
    }
    const aggBatchRadios = document.getElementsByName("batch-aggregated");
    aggBatchRadios.forEach(radio => {
        radio.checked = (radio.value === "false");
    });
    const qtyEl = document.getElementById("batch-qty");
    if (qtyEl) {
        const grp = qtyEl.closest(".form-group");
        if (grp) grp.classList.remove("hidden");
    }
    const prodId = document.getElementById("batch-product-id");
    if (prodId) prodId.value = "";
    const prodInput = document.getElementById("batch-product-input");
    if (prodInput) prodInput.value = "";
    
    const secRatio = document.getElementById("batch-ratio-sec");
    if (secRatio) secRatio.value = 10;
    const terRatio = document.getElementById("batch-ratio-ter");
    if (terRatio) terRatio.value = 10;
    updateRecipeCalculation();

    generateNewBatchIdempotencyKey();
}

// ----------------- Product Dropdown Select Logic -----------------
function populateProductDropdowns() {
    const gtinDatalist = document.getElementById("gtin-product-datalist");
    const batchDatalist = document.getElementById("batch-product-datalist");
    const gtinSelect = document.getElementById("gtin-product-select");
    const batchSelect = document.getElementById("batch-product-select");
    
    if (gtinDatalist) {
        gtinDatalist.innerHTML = "";
        registeredProducts.forEach(p => {
            const opt = document.createElement("option");
            opt.value = `${p.name} (${p.product_id})`;
            gtinDatalist.appendChild(opt);
        });
    }

    if (batchDatalist) {
        batchDatalist.innerHTML = "";
        registeredProducts.forEach(p => {
            const opt = document.createElement("option");
            opt.value = `${p.name} (${p.product_id})`;
            batchDatalist.appendChild(opt);
        });
    }

    if (gtinSelect) {
        gtinSelect.innerHTML = '<option value="" disabled selected>-- Select Product --</option>';
        registeredProducts.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p.product_id;
            opt.textContent = `${p.name} (${p.product_id})`;
            gtinSelect.appendChild(opt);
        });
    }
    
    if (batchSelect) {
        batchSelect.innerHTML = '<option value="" disabled selected>-- Select Product --</option>';
        registeredProducts.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p.product_id;
            opt.textContent = `${p.name} (${p.product_id})`;
            batchSelect.appendChild(opt);
        });
    }
}

function setupProductDropdownListeners() {
    function handleProductMatch(val, isBatch) {
        if (!val) return;
        const cleanVal = val.trim().toLowerCase();
        const m = registeredProducts.find(p => 
            p.product_id.toLowerCase() === cleanVal ||
            cleanVal.includes(`(${p.product_id.toLowerCase()})`) ||
            p.name.toLowerCase() === cleanVal
        );
        if (m) {
            if (isBatch) {
                const prodIdEl = document.getElementById("batch-product-id");
                if (prodIdEl) prodIdEl.value = m.product_id;
                const mfgEl = document.getElementById("batch-manufacturer");
                if (mfgEl && m.manufacturer) mfgEl.value = m.manufacturer;
                const plantEl = document.getElementById("batch-plant");
                if (plantEl && m.plant) plantEl.value = m.plant;
                updateBatchGtinFromStore();
            } else {
                const prodIdEl = document.getElementById("gtin-product-id");
                if (prodIdEl) prodIdEl.value = m.product_id;
                const codeEl = document.getElementById("gtin-productcode");
                if (codeEl) codeEl.value = m.product_id;
                const gtinEl = document.getElementById("gtin-val");
                if (gtinEl && m.gtin) gtinEl.value = m.gtin;
                const mfgEl = document.getElementById("gtin-manufacturer");
                if (mfgEl && m.manufacturer) mfgEl.value = m.manufacturer;
                const plantEl = document.getElementById("gtin-plant");
                if (plantEl && m.plant) plantEl.value = m.plant;
            }
        }
    }

    const gtinInput = document.getElementById("gtin-product-input");
    if (gtinInput) {
        gtinInput.addEventListener("input", (e) => handleProductMatch(e.target.value, false));
        gtinInput.addEventListener("change", (e) => handleProductMatch(e.target.value, false));
    }
    const gtinSelect = document.getElementById("gtin-product-select");
    if (gtinSelect) {
        gtinSelect.addEventListener("change", (e) => handleProductMatch(e.target.value, false));
    }

    const batchInput = document.getElementById("batch-product-input");
    if (batchInput) {
        batchInput.addEventListener("input", (e) => handleProductMatch(e.target.value, true));
        batchInput.addEventListener("change", (e) => handleProductMatch(e.target.value, true));
    }
    const batchSelect = document.getElementById("batch-product-select");
    if (batchSelect) {
        batchSelect.addEventListener("change", (e) => handleProductMatch(e.target.value, true));
    }
}

// ----------------- Serial No Type & Packaging Category Handlers -----------------
function setupSerialTypeHandlers() {
    const radioSgtin = document.querySelector('input[name="gtin-serial-type"][value="SGTIN"]');
    const radioSscc = document.querySelector('input[name="gtin-serial-type"][value="SSCC"]');
    const pkgCategorySelect = document.getElementById("gtin-pkgcategory");
    const pkgLevelSelect = document.getElementById("gtin-pkglevel");
    const helperContainer = document.getElementById("serial-type-helper");
    const helperText = document.getElementById("serial-type-helper-text");

    function updateHelper(type) {
        if (!helperContainer || !helperText) return;
        if (type === "SSCC") {
            helperContainer.style.background = "#fff8e6";
            helperContainer.style.borderColor = "#fde293";
            helperContainer.style.color = "#7c4a03";
            helperText.innerHTML = `<strong>SSCC Mode Active:</strong> Encodes AI (00) Serial Shipping Container Code for logistics packaging (Tertiary / Pallet).`;
        } else {
            helperContainer.style.background = "#eaf4fe";
            helperContainer.style.borderColor = "#d0e7fc";
            helperContainer.style.color = "#08445f";
            helperText.innerHTML = `<strong>SGTIN Mode Active:</strong> Encodes AI (01) GTIN + AI (21) Serial Number for saleable trade packaging (Primary / Secondary / Inner).`;
        }
    }

    // Radio change listeners
    document.querySelectorAll('input[name="gtin-serial-type"]').forEach(radio => {
        radio.addEventListener("change", (e) => {
            const val = e.target.value;
            if (val === "SSCC") {
                if (pkgCategorySelect && (!["Tertiary", "Pallet"].includes(pkgCategorySelect.value))) {
                    pkgCategorySelect.value = "Tertiary";
                }
                if (pkgLevelSelect) pkgLevelSelect.value = "Tertiary";
            } else {
                if (pkgCategorySelect && (!["Primary", "Secondary", "Inner"].includes(pkgCategorySelect.value))) {
                    pkgCategorySelect.value = "Primary";
                }
                if (pkgLevelSelect && pkgCategorySelect) pkgLevelSelect.value = pkgCategorySelect.value;
            }
            updateHelper(val);
        });
    });

    // Packaging Category dropdown change listener
    if (pkgCategorySelect) {
        pkgCategorySelect.addEventListener("change", (e) => {
            const val = e.target.value;
            if (val === "Tertiary" || val === "Pallet") {
                if (radioSscc) radioSscc.checked = true;
                if (pkgLevelSelect && val === "Tertiary") pkgLevelSelect.value = "Tertiary";
                updateHelper("SSCC");
            } else {
                if (radioSgtin) radioSgtin.checked = true;
                if (pkgLevelSelect) pkgLevelSelect.value = val;
                updateHelper("SGTIN");
            }
        });
    }

    // Top Packaging Level dropdown change listener
    if (pkgLevelSelect) {
        pkgLevelSelect.addEventListener("change", (e) => {
            const val = e.target.value;
            if (val === "Tertiary") {
                if (radioSscc) radioSscc.checked = true;
                if (pkgCategorySelect) pkgCategorySelect.value = "Tertiary";
                updateHelper("SSCC");
            } else if (["Primary", "Secondary", "Inner"].includes(val)) {
                if (radioSgtin) radioSgtin.checked = true;
                if (pkgCategorySelect) pkgCategorySelect.value = val;
                updateHelper("SGTIN");
            }
        });
    }

    // Batch Packaging Level dynamic GTIN resolution
    const batchPkgLevel = document.getElementById("batch-pkglevel");
    if (batchPkgLevel) {
        batchPkgLevel.addEventListener("change", () => {
            updateBatchGtinFromStore();
        });
    }
}

// ----------------- Segmented Status Toggle Listeners -----------------
function setupStatusToggleListeners() {
    document.querySelectorAll(".status-toggle-group input[type='radio']").forEach(radio => {
        radio.addEventListener("change", () => {
            const group = radio.closest(".status-toggle-group");
            if (!group) return;
            group.querySelectorAll(".status-toggle-btn").forEach(btn => btn.classList.remove("is-checked"));
            const parentBtn = radio.closest(".status-toggle-btn");
            if (parentBtn && radio.checked) {
                parentBtn.classList.add("is-checked");
            }
        });
    });
}

function updateBatchGtinFromStore() {
    const prodIdEl = document.getElementById("batch-product-id");
    const pkgLevelEl = document.getElementById("batch-pkglevel");
    const gtinEl = document.getElementById("batch-gtin");
    const badgeEl = document.getElementById("batch-gtin-type-badge");
    const aggCheckbox = document.getElementById("batch-aggregation");

    if (!prodIdEl || !prodIdEl.value) {
        if (badgeEl) badgeEl.classList.add("hidden");
        return;
    }

    const productId = prodIdEl.value;
    const pkgLevel = pkgLevelEl ? pkgLevelEl.value : "";

    // Find GTIN matching both product_id and packaging_level
    let matched = null;
    if (pkgLevel && registeredGtins && registeredGtins.length > 0) {
        matched = registeredGtins.find(g => 
            g.product_id === productId && 
            g.packaging_level.toLowerCase() === pkgLevel.toLowerCase() &&
            g.enable_gtin
        );
    }

    // Fallback if no exact packaging level match: any active GTIN for product
    if (!matched && registeredGtins && registeredGtins.length > 0) {
        matched = registeredGtins.find(g => g.product_id === productId && g.enable_gtin);
    }

    if (matched) {
        if (gtinEl) gtinEl.value = matched.gtin;
        if (badgeEl) {
            badgeEl.textContent = `${matched.serial_no_type || "SGTIN"} (${matched.packaging_category || matched.packaging_level})`;
            badgeEl.className = `badge ${matched.serial_no_type === "SSCC" ? "badge-warning" : "badge-info"}`;
            badgeEl.classList.remove("hidden");
        }
        // If SSCC category, auto check package aggregation
        if (matched.serial_no_type === "SSCC" && aggCheckbox) {
            aggCheckbox.checked = true;
        }
    } else {
        // Fallback to Product master GTIN
        const prod = registeredProducts.find(p => p.product_id === productId);
        if (prod && prod.gtin) {
            if (gtinEl) gtinEl.value = prod.gtin;
            if (badgeEl) {
                badgeEl.textContent = "SGTIN (Product Default)";
                badgeEl.className = "badge badge-secondary";
                badgeEl.classList.remove("hidden");
            }
        } else {
            if (badgeEl) badgeEl.classList.add("hidden");
        }
    }
    updateRecipeCalculation();
}

// ----------------- Image Base64 Conversion -----------------
function setupFileHandlers() {
    const fileInput = document.getElementById("prod-image");
    const preview = document.getElementById("prod-img-preview");
    const sizeInfo = document.getElementById("prod-img-size-info");

    fileInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Frontend check for size (Max 3KB = 3072 bytes)
        if (file.size > 3072) {
            alert("Image size should be less than 3kb.");
            fileInput.value = "";
            preview.classList.add("hidden");
            sizeInfo.textContent = "";
            productBase64Image = "";
            return;
        }

        const reader = new FileReader();
        reader.onload = (event) => {
            productBase64Image = event.target.result;
            preview.src = productBase64Image;
            preview.classList.remove("hidden");
            sizeInfo.textContent = `Size: ${(file.size / 1024).toFixed(2)} KB`;
        };
        reader.readAsDataURL(file);
    });
}

// Toggle DSCSA & EUFMD panels in product setup
function toggleAuthorityPanels(authority) {
    const dscsaPanel = document.getElementById("panel-dscsa");
    const eufmdPanel = document.getElementById("panel-eufmd");

    dscsaPanel.classList.add("hidden");
    eufmdPanel.classList.add("hidden");

    if (authority === "DSCSA") {
        dscsaPanel.classList.remove("hidden");
    } else if (authority === "EUFMD") {
        eufmdPanel.classList.remove("hidden");
    }
}

// ----------------- Form Handlers & Event Listeners -----------------
function setupEventListeners() {
    // Product setup authority changer
    safeAddListener("prod-regulatory", "change", (e) => {
        toggleAuthorityPanels(e.target.value);
    });

    // Product setup Save
    safeAddListener("product-form", "submit", handleProductSaveSubmit);
    
    // Product setup Cancel & Add
    safeAddListener("prod-cancel-btn", "click", () => {
        switchView("view-product-list");
    });
    safeAddListener("btn-goto-add-product", "click", () => {
        resetProductForm();
        switchView("view-product-add");
    });

    // GTIN setup Save & Add
    safeAddListener("gtin-form", "submit", handleGtinSaveSubmit);
    safeAddListener("gtin-cancel-btn", "click", () => {
        switchView("view-gtin-list");
    });
    safeAddListener("btn-goto-add-gtin", "click", () => {
        resetGtinForm();
        switchView("view-gtin-add");
    });

    // Batch setup Save & Add
    safeAddListener("batch-form", "submit", handleBatchSaveSubmit);
    safeAddListener("batch-cancel-btn", "click", (e) => {
        e.preventDefault();
        switchView("view-batch-list");
    });
    safeAddListener("btn-goto-add-batch", "click", () => {
        resetBatchForm();
        switchView("view-batch-add");
    });
    safeAddListener("batch-uuid-btn", "click", generateNewBatchIdempotencyKey);

    // Import Simulations
    safeAddListener("prod-import-btn", "click", () => showImportModal("Products"));
    safeAddListener("gtin-import-btn", "click", () => showImportModal("GTINs"));
    safeAddListener("batch-import-btn", "click", () => showImportModal("Batches"));

    safeAddListener("btn-mock-import-close", "click", hideImportModal);
    safeAddListener("btn-mock-import-confirm", "click", executeMockImport);

    // Audit Log Details Close
    safeAddListener("btn-audit-modal-close", "click", () => {
        const modal = document.getElementById("audit-details-modal");
        if (modal) modal.classList.add("hidden");
    });

    // Product Filter Row
    safeAddListener("btn-filter-products", "click", () => {
        const mfgEl = document.getElementById("filt-prod-mfg");
        const plantEl = document.getElementById("filt-prod-plant");
        const mktEl = document.getElementById("filt-prod-mkt");
        const regEl = document.getElementById("filt-prod-reg");
        const searchEl = document.getElementById("filt-prod-search");

        const mfg = mfgEl ? mfgEl.value : "";
        const plant = plantEl ? plantEl.value : "";
        const mkt = mktEl ? mktEl.value : "";
        const reg = regEl ? regEl.value : "";
        const search = searchEl ? searchEl.value.trim().toLowerCase() : "";

        let filtered = registeredProducts;
        if (mfg) filtered = filtered.filter(p => p.manufacturer === mfg);
        if (plant) filtered = filtered.filter(p => p.plant === plant);
        if (mkt) filtered = filtered.filter(p => p.marketing_level === mkt);
        if (reg) filtered = filtered.filter(p => p.regulatory_authority === reg);
        if (search) {
            filtered = filtered.filter(p => 
                p.product_id.toLowerCase().includes(search) || 
                p.name.toLowerCase().includes(search)
            );
        }
        renderProductList(filtered);
    });

    // GTIN Filter Row
    safeAddListener("btn-filter-gtins", "click", () => {
        const mfgEl = document.getElementById("filt-gtin-mfg");
        const plantEl = document.getElementById("filt-gtin-plant");
        const searchEl = document.getElementById("filt-gtin-search");

        const mfg = mfgEl ? mfgEl.value : "";
        const plant = plantEl ? plantEl.value : "";
        const search = searchEl ? searchEl.value.trim().toLowerCase() : "";

        let filtered = registeredGtins;
        if (mfg) filtered = filtered.filter(g => g.manufacturer === mfg);
        if (plant) filtered = filtered.filter(g => g.plant === plant);
        if (search) {
            filtered = filtered.filter(g => 
                g.product_code.toLowerCase().includes(search) || 
                g.gtin.includes(search)
            );
        }
        renderGtinList(filtered);
    });

    // SGTIN Event Listeners
    safeAddListener("sgtin-gtin", "input", (e) => {
        e.target.value = e.target.value.replace(/\D/g, "").slice(0, 14);
    });
    safeAddListener("sgtin-form", "submit", generateSgtinCsv);

    // Verification Event Listeners
    safeAddListener("search-btn", "click", performSerialLookup);
    safeAddListener("search-serial", "keypress", (e) => {
        if (e.key === "Enter") performSerialLookup();
    });
    safeAddListener("update-status-btn", "click", performSerialTransition);

    // Reconcile and Summary Modal Buttons
    safeAddListener("btn-submit-reconcile", "click", () => {
        if (window.submitReconciliation) window.submitReconciliation();
    });
    safeAddListener("btn-close-reconcile-modal", "click", () => {
        if (window.closeReconcileModal) window.closeReconcileModal();
    });
    safeAddListener("btn-close-summary-modal", "click", () => {
        if (window.closeSummaryModal) window.closeSummaryModal();
    });

    // Live Recipe Calculation Listeners
    safeAddListener("batch-qty", "input", updateRecipeCalculation);
    safeAddListener("batch-ratio-sec", "input", updateRecipeCalculation);
    safeAddListener("batch-ratio-ter", "input", updateRecipeCalculation);

    // Packaging Lines & I/O Listeners
    safeAddListener("line-form", "submit", handleLineSaveSubmit);
    safeAddListener("line-io-form", "submit", handleLineIoSaveSubmit);
    safeAddListener("btn-test-line-io", "click", () => window.testLineConnectivity());
    safeAddListener("io-select-line", "change", (e) => populateIoForm(e.target.value));
    safeAddListener("io-select-protocol", "change", (e) => toggleIoPanels(e.target.value));
    safeAddListener("line-protocol-select", "change", (e) => {
        const directInput = document.getElementById("line-api-endpoint");
        const lineIdVal = (document.getElementById("line-id-input")?.value || "line-04").toLowerCase();
        if (directInput && !directInput.value && e.target.value === "DIRECT_API") {
            directInput.value = `http://127.0.0.1:8000/api/v1/l2/mock-controller/${lineIdVal}`;
        }
    });

    // Code Pool Reservoir Listeners
    safeAddListener("pool-import-form", "submit", handleCodePoolImportSubmit);
    safeAddListener("pool-import-product", "change", (e) => {
        const prodId = e.target.value;
        const p = registeredProducts.find(prod => prod.product_id === prodId);
        const gtinInput = document.getElementById("pool-import-gtin");
        if (gtinInput && p && p.gtin) {
            gtinInput.value = p.gtin;
        } else {
            const g = registeredGtins.find(gt => gt.product_id === prodId);
            if (gtinInput && g && g.gtin) gtinInput.value = g.gtin;
        }
    });
    safeAddListener("pool-import-file", "change", (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (evt) => {
            const textarea = document.getElementById("pool-import-serials");
            if (textarea) textarea.value = evt.target.result;
        };
        reader.readAsText(file);
    });

    // XML Report & Detailed Report Listeners
    safeAddListener("btn-preview-xml", "click", previewSelectedXml);
    safeAddListener("btn-download-selected-xml", "click", downloadSelectedXml);
    safeAddListener("btn-load-detail-report", "click", loadDetailedBatchReport);
}

// ----------------- Save Handlers -----------------
async function handleProductSaveSubmit(e) {
    e.preventDefault();

    const getVal = (id) => {
        const el = document.getElementById(id);
        return el ? el.value.trim() : "";
    };

    const regulatory = getVal("prod-regulatory");
    const codeProvider = getVal("prod-codeprovider");
    const manufacturer = getVal("prod-manufacturer");
    const plant = getVal("prod-plant");
    const marketingLevel = getVal("prod-marketinglevel");
    const productId = getVal("prod-id").toUpperCase();
    const name = getVal("prod-name");
    const gtin = getVal("prod-gtin");
    const itemCodeType = getVal("prod-itemcode-type");
    const itemCode = getVal("prod-itemcode");

    // Check validations
    if (!manufacturer) return alert("Please Select Manufacturer");
    if (!plant) return alert("Please Select Plant.");
    if (!marketingLevel) return alert("Please Select Marketing Level.");
    if (!productId) return alert("Please enter product code");
    if (!name) return alert("Please enter Product Name.");
    
    if (regulatory === "DSCSA") {
        const ndc = getVal("prod-ndc");
        const ndcType = getVal("prod-ndctype");
        if (!ndc) return alert("Please enter NDC");
        if (!ndcType) return alert("Please select NDC Type");
    } else if (regulatory === "EUFMD") {
        const countryType = getVal("prod-countrycode-type");
        const countryCode = getVal("prod-countrycode");
        if (!countryType || !countryCode) return alert("Please enter Country Drug Code");
        if (!countryType) return alert("Please enter Internal Material Number");
    }

    if (!itemCodeType) return alert("Please select Item Code Type");
    if (!itemCode) return alert("Please enter Item Code");
    if (!productBase64Image) return alert("Please enter image");

    const activeRadios = document.getElementsByName("prod-active");
    let isActive = true;
    activeRadios.forEach(r => { if (r.checked) isActive = r.value === "true"; });

    const payload = {
        product_id: productId,
        name: name,
        gtin: gtin,
        status: "ACTIVE",
        profile: {
            length: 20,
            alphabet: "23456789ABCDEFGHJKMNPQRSTVWXYZ",
            require_alpha: true,
            require_numeric: true,
            allow_duplicate_characters: false
        },
        regulatory_authority: regulatory || null,
        code_provider: codeProvider || null,
        manufacturer: manufacturer,
        plant: plant,
        marketing_level: marketingLevel,
        product_code: productId,
        product_name_2: getVal("prod-name2") || null,
        product_name_3: getVal("prod-name3") || null,
        stk: getVal("prod-stk") || null,
        manufactured_by: getVal("prod-mfgby") || null,
        distributed_by: getVal("prod-distby") || null,
        storage_condition: getVal("prod-storage") || null,
        license: getVal("prod-license") || null,
        generic_name: getVal("prod-generic") || null,
        composition: getVal("prod-composition") || null,
        usage_dose: getVal("prod-usagedose") || null,
        remark: getVal("prod-remark") || null,
        product_image: productBase64Image,
        unit_price: getVal("prod-price") || null,
        ndc: getVal("prod-ndc") || null,
        ndc_type: getVal("prod-ndctype") || null,
        country_drug_code_type: getVal("prod-countrycode-type") || null,
        country_drug_code: getVal("prod-countrycode") || null,
        internal_material_number: getVal("prod-materialnumber") || null,
        nnhrn: getVal("prod-nnhrn") || null,
        nhrn_ai_type: getVal("prod-nhrnai-type") || null,
        item_code_type: itemCodeType,
        item_code: itemCode,
        is_active: isActive,
        additional_field_1: getVal("prod-add1") || null,
        additional_field_2: getVal("prod-add2") || null
    };

    const msg = document.getElementById("prod-message");
    msg.textContent = "Saving product...";
    msg.className = "form-message";

    try {
        const url = currentProductFormMode === "ADD" ? "/api/v1/products" : `/api/v1/products/${currentProductFormId}`;
        const method = currentProductFormMode === "ADD" ? "POST" : "PUT";
        
        const res = await fetch(url, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok) {
            msg.textContent = `Product saved successfully: ${data.product_id}`;
            msg.className = "form-message success";
            loadProducts();
            loadAuditLogs();
            setTimeout(() => {
                switchView("view-product-list");
                resetProductForm();
            }, 1000);
        } else {
            msg.textContent = `Error: ${data.detail || "Failed to save product."}`;
            msg.className = "form-message error";
        }
    } catch (err) {
        console.error("Product save error:", err);
        msg.textContent = `Error: ${err.message || "connection failed."}`;
        msg.className = "form-message error";
    }
}

async function handleGtinSaveSubmit(e) {
    e.preventDefault();

    const manufacturer = document.getElementById("gtin-manufacturer").value;
    const plant = document.getElementById("gtin-plant").value;
    let productId = document.getElementById("gtin-product-id").value;
    const productInputVal = document.getElementById("gtin-product-input") ? document.getElementById("gtin-product-input").value.trim() : "";
    if (!productId && productInputVal) {
        const m = registeredProducts.find(p => 
            p.product_id.toLowerCase() === productInputVal.toLowerCase() ||
            productInputVal.toLowerCase().includes(`(${p.product_id.toLowerCase()})`) ||
            p.name.toLowerCase() === productInputVal.toLowerCase()
        );
        if (m) {
            productId = m.product_id;
            document.getElementById("gtin-product-id").value = m.product_id;
        }
    }

    const packagingLevel = document.getElementById("gtin-pkglevel").value;
    const packagingSize = document.getElementById("gtin-pkgsize").value.trim();
    const gtin = document.getElementById("gtin-val").value.trim();
    const limit = parseInt(document.getElementById("gtin-limit").value, 10);
    const codeLength = parseInt(document.getElementById("gtin-codelen").value, 10);
    const caseQtyInput = document.getElementById("gtin-caseqty").value;
    const caseQuantity = caseQtyInput ? parseInt(caseQtyInput, 10) : null;

    // Validations
    if (!manufacturer) return alert("Please Select Manufactures");
    if (!plant) return alert("Please Select Plant.");
    if (!productId) return alert("Please enter Product.");
    if (!packagingLevel) return alert("Please enter Packaging Level.");
    if (!packagingSize) return alert("Please enter Packaging Size.");
    if (!gtin) return alert("Please Select GTIN.");
    if (packagingLevel.toUpperCase() === "PRIMARY") {
        if (!caseQuantity || caseQuantity === 0) return alert("Please enter Case Quantity.");
    }
    if (!limit) return alert("Please enter Limit.");
    if (!codeLength) return alert("Please enter code length");

    const enabledRadios = document.getElementsByName("gtin-enabled");
    let enableGtin = true;
    enabledRadios.forEach(r => { if (r.checked) enableGtin = r.value === "true"; });

    const serialTypeRadio = document.querySelector('input[name="gtin-serial-type"]:checked');
    const serialNoType = serialTypeRadio ? serialTypeRadio.value : "SGTIN";
    const pkgCategoryEl = document.getElementById("gtin-pkgcategory");
    const packagingCategory = pkgCategoryEl ? pkgCategoryEl.value : (serialNoType === "SSCC" ? "Tertiary" : "Primary");

    const payload = {
        manufacturer,
        plant,
        packaging_level: packagingLevel,
        product_id: productId,
        product_code: productId,
        packing_size: packagingSize,
        gtin,
        enable_gtin: enableGtin,
        case_quantity: caseQuantity,
        limit,
        code_length: codeLength,
        serial_no_type: serialNoType,
        packaging_category: packagingCategory
    };

    const msg = document.getElementById("gtin-message");
    msg.textContent = "Saving GTIN config...";
    msg.className = "form-message";

    try {
        const url = currentGtinFormMode === "ADD" ? "/api/v1/gtin-store" : `/api/v1/gtin-store/${currentGtinFormId}`;
        const method = currentGtinFormMode === "ADD" ? "POST" : "PUT";

        const res = await fetch(url, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok) {
            msg.textContent = `GTIN saved successfully: ${data.gtin}`;
            msg.className = "form-message success";
            loadGtins();
            loadAuditLogs();
            setTimeout(() => {
                switchView("view-gtin-list");
                resetGtinForm();
            }, 1000);
        } else {
            msg.textContent = `Error: ${data.detail || "Failed to save GTIN."}`;
            msg.className = "form-message error";
        }
    } catch (err) {
        console.error("GTIN save error:", err);
        msg.textContent = `Error: ${err.message || "connection failed."}`;
        msg.className = "form-message error";
    }
}

async function handleBatchSaveSubmit(e) {
    e.preventDefault();

    const getVal = (id) => {
        const el = document.getElementById(id);
        return el ? el.value.trim() : "";
    };

    const manufacturer = getVal("batch-manufacturer");
    const plant = getVal("batch-plant");
    const packagingLevel = getVal("batch-pkglevel");
    
    let productId = getVal("batch-product-id");
    const productInputVal = getVal("batch-product-input");
    if (!productId && productInputVal) {
        const m = registeredProducts.find(p => 
            p.product_id.toLowerCase() === productInputVal.toLowerCase() ||
            productInputVal.toLowerCase().includes(`(${p.product_id.toLowerCase()})`) ||
            p.name.toLowerCase() === productInputVal.toLowerCase()
        );
        if (m) {
            productId = m.product_id;
            const pidEl = document.getElementById("batch-product-id");
            if (pidEl) pidEl.value = m.product_id;
        }
    }

    const packagingSize = getVal("batch-pkgsize");
    const workOrder = getVal("batch-workorder");
    const batchLot = getVal("batch-num").toUpperCase();
    const gtin = getVal("batch-gtin");
    const mfgDateRaw = getVal("batch-mfgdate");
    const expiryDateRaw = getVal("batch-expiry");
    const mfgDate = convertDateInputToMfgDisplay(mfgDateRaw);
    const expiryDate = convertDateInputToApiExpiry(expiryDateRaw);
    const qtyVal = getVal("batch-qty");
    const quantity = qtyVal ? parseInt(qtyVal, 10) : 10;
    const idempotencyKey = getVal("batch-idempotency");

    // Validations matching alternate flow specs
    if (!manufacturer) return alert("Please Select Manufactures");
    if (!plant) return alert("Please Select Plant.");
    if (!packagingLevel) return alert("Please enter Packaging Level.");
    if (!productId) return alert("Please enter Product.");
    if (!packagingSize) return alert("Please enter Packaging Size.");
    if (!workOrder) return alert("Please enter Work Order No.");
    if (!batchLot) return alert("Please enter Batch Number.");
    if (!gtin) return alert("Please Select GTIN.");
    if (!mfgDateRaw) return alert("Please enter Manufacturing Date.");
    if (!expiryDateRaw) return alert("Please enter Expiry Date.");
    if (!quantity || quantity <= 0) return alert("Please enter valid Quantity.");

    const enabledRadios = document.getElementsByName("batch-enabled");
    let isEnabled = true;
    enabledRadios.forEach(r => { if (r.checked) isEnabled = r.value === "true"; });

    const aggBatchRadios = document.getElementsByName("batch-aggregated");
    let isAggregatedBatch = false;
    aggBatchRadios.forEach(r => { if (r.checked) isAggregatedBatch = r.value === "true"; });

    const aggEl = document.getElementById("batch-aggregation");
    const packageAggregation = aggEl ? aggEl.checked : false;
    const parentEl = document.getElementById("batch-parentcode");
    const parentCodeRequired = parentEl ? parentEl.checked : false;

    const lineId = getVal("batch-line") || "Line 01";
    const ioChannel = getVal("batch-io-channel") || "DIRECT_API";
    const secRatioVal = getVal("batch-ratio-sec");
    const terRatioVal = getVal("batch-ratio-ter");
    const secRatio = secRatioVal ? parseInt(secRatioVal, 10) : 10;
    const terRatio = terRatioVal ? parseInt(terRatioVal, 10) : 10;

    const payload = {
        manufacturer,
        plant,
        packaging_level: packagingLevel,
        product_id: productId,
        packaging_size: packagingSize,
        work_order_no: workOrder,
        batch_lot: batchLot,
        gtin,
        mfg_date: mfgDate,
        expiry_date: expiryDate,
        quantity,
        is_enabled: isEnabled,
        package_aggregation: packageAggregation,
        parent_code_required: parentCodeRequired,
        aggregated_batch: isAggregatedBatch,
        idempotency_key: idempotencyKey,
        line_id: lineId,
        io_channel: ioChannel,
        secondary_ratio: secRatio,
        tertiary_ratio: terRatio
    };

    const msg = document.getElementById("batch-message");
    msg.textContent = "Saving batch & generating serial codes...";
    msg.className = "form-message";

    const formEl = document.getElementById("batch-form");
    const formMode = (formEl && formEl.dataset.mode) || "ADD";
    const editBatchId = (formEl && formEl.dataset.batchId) || "";

    try {
        const url = formMode === "ADD" ? "/api/v1/batches" : `/api/v1/batches/${editBatchId}`;
        const method = formMode === "ADD" ? "POST" : "PUT";

        const res = await fetch(url, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok) {
            msg.textContent = `Batch saved successfully: ${data.batch_id}`;
            msg.className = "form-message success";
            loadBatches();
            loadAuditLogs();
            setTimeout(() => {
                switchView("view-batch-list");
                resetBatchForm();
            }, 1000);
        } else {
            msg.textContent = `Error: ${data.detail || "Failed to register batch."}`;
            msg.className = "form-message error";
        }
    } catch (err) {
        console.error("Batch save error:", err);
        msg.textContent = `Error: ${err.message || "connection failed."}`;
        msg.className = "form-message error";
    }
}

// ----------------- Mock Excel Import Simulation -----------------
let activeImportModule = "";
function showImportModal(moduleName) {
    activeImportModule = moduleName;
    document.getElementById("mock-import-modal").classList.remove("hidden");
}

function hideImportModal() {
    document.getElementById("mock-import-modal").classList.add("hidden");
    document.getElementById("mock-excel-file").value = "";
}

function executeMockImport() {
    const file = document.getElementById("mock-excel-file").files[0];
    if (!file) {
        alert("Please select a file to import.");
        return;
    }
    
    // Simulate import
    alert(`Success: 5 mock records imported into ${activeImportModule} master store database.`);
    loadAllData();
    hideImportModal();
}

// ----------------- Client-Friendly Audit Trail Text Formatter -----------------
const AUDIT_FIELD_LABELS = {
    "id": "Record ID",
    "batch_id": "Batch ID",
    "batch_lot": "Batch / Lot Number",
    "product_id": "Product Code / ID",
    "product_code": "Product Code",
    "product_name": "Product Name",
    "gtin": "GTIN (GS1 Barcode)",
    "status": "Operational Status",
    "mfg_date": "Manufacturing Date",
    "expiry_date": "Expiry Date",
    "manufacturer": "Manufacturer",
    "plant": "Production Plant",
    "packaging_level": "Packaging Level",
    "packaging_size": "Packaging Size",
    "packing_size": "Packing Size",
    "packaging_category": "Packaging Category",
    "package_aggregation": "Package Aggregation",
    "parent_code_required": "Parent Code Required",
    "aggregated_batch": "Aggregated Batch",
    "work_order_no": "Work Order No.",
    "requested_quantity": "Requested Target Quantity",
    "generated_quantity": "Total Generated Serials",
    "start_sequence": "Start Sequence",
    "end_sequence": "End Sequence",
    "secondary_ratio": "Secondary Ratio",
    "tertiary_ratio": "Tertiary Ratio",
    "primary_quantity": "Primary Count",
    "secondary_quantity": "Secondary Count",
    "tertiary_quantity": "Tertiary Count",
    "yield_percentage": "Reconciliation Yield",
    "good_count": "Good Units Inspected",
    "rejected_count": "Rejected / Defect Units",
    "unused_returned_count": "Unused Codes Returned to Reservoir",
    "reconciled_good_count": "Good Packs Reconciled",
    "reconciled_rejected_count": "Rejected Packs Reconciled",
    "reconciled_unused_count": "Unused Codes Reconciled",
    "is_locked": "Batch Locked Status",
    "is_enabled": "Active Status",
    "enable_gtin": "GTIN Active Status",
    "line_id": "Packaging Line ID",
    "line_name": "Line Name",
    "line_code": "Line Code",
    "io_channel": "Line I/O Interface",
    "case_quantity": "Case Pack Quantity",
    "limit": "Serial Generation Limit",
    "code_length": "Barcode Code Length",
    "serial_no_type": "Serial Number Standard",
    "username": "User Account ID",
    "display_name": "User Full Name",
    "role_name": "Assigned Role",
    "role_id": "Role ID",
    "description": "Role / Record Description",
    "permissions": "Assigned Module Permissions",
    "last_login": "Last Login Timestamp",
    "created_at": "Record Creation Timestamp",
    "updated_at": "Record Update Timestamp",
    "client_ip": "Client IP Address",
    "request_id": "Request Trace ID"
};

function formatAuditFieldLabel(key) {
    if (AUDIT_FIELD_LABELS[key]) return AUDIT_FIELD_LABELS[key];
    return key.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
}

function formatAuditValueAsText(key, val) {
    if (val === null || val === undefined || val === "") {
        return '<span style="color: #94a3b8; font-style: italic;">None / Unset</span>';
    }
    if (typeof val === "boolean") {
        return val ? '<span class="badge badge-success" style="background: #e6f4ea; color: #137333; padding: 2px 8px; border-radius: 4px; font-weight: 600;">Yes (Active)</span>' 
                   : '<span class="badge badge-secondary" style="background: #f1f3f4; color: #5f6368; padding: 2px 8px; border-radius: 4px; font-weight: 600;">No (Inactive)</span>';
    }
    if (key === "yield_percentage" && typeof val === "number") {
        return `<strong>${val}%</strong>`;
    }
    if (key === "permissions" && typeof val === "object") {
        const rows = [];
        for (const [mod, acts] of Object.entries(val)) {
            const modLabel = mod.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
            let actList = "";
            if (Array.isArray(acts)) {
                actList = acts.map(a => a.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase())).join(", ");
            } else if (typeof acts === "object" && acts !== null) {
                actList = Object.keys(acts).filter(k => acts[k]).map(k => k.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase())).join(", ");
            } else {
                actList = String(acts);
            }
            rows.push(`<div style="margin-bottom: 3px;"><strong>${modLabel}:</strong> <span style="color: #0f5d7f;">${actList || 'No Actions'}</span></div>`);
        }
        return rows.length ? `<div style="font-size: 0.85rem; line-height: 1.4;">${rows.join("")}</div>` : "None";
    }
    if (typeof val === "object") {
        try {
            const entries = Object.entries(val).map(([k, v]) => `<div><strong>${formatAuditFieldLabel(k)}:</strong> ${String(v)}</div>`);
            return `<div style="font-size: 0.85rem;">${entries.join("")}</div>`;
        } catch (_) {
            return JSON.stringify(val);
        }
    }
    if (typeof val === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(val)) {
        try {
            return `<span>${new Date(val).toLocaleString()}</span>`;
        } catch (_) {}
    }
    return `<span>${escapeHtml(String(val))}</span>`;
}

window.toggleAuditRawView = function() {
    const rawSec = document.getElementById("audit-raw-section");
    const textSec = document.getElementById("audit-text-container");
    const toggleBtn = document.getElementById("btn-toggle-audit-view");
    if (!rawSec || !textSec) return;

    if (rawSec.classList.contains("hidden")) {
        rawSec.classList.remove("hidden");
        textSec.classList.add("hidden");
        if (toggleBtn) toggleBtn.textContent = "Switch to Client Text View";
    } else {
        rawSec.classList.add("hidden");
        textSec.classList.remove("hidden");
        if (toggleBtn) toggleBtn.textContent = "View Technical JSON";
    }
};

window.viewAuditDetails = function(id, prevValEscaped, newValEscaped) {
    // 1. Reset toggle state to always show client text by default
    const rawSec = document.getElementById("audit-raw-section");
    const textSec = document.getElementById("audit-text-container");
    const toggleBtn = document.getElementById("btn-toggle-audit-view");
    if (rawSec) rawSec.classList.add("hidden");
    if (textSec) textSec.classList.remove("hidden");
    if (toggleBtn) toggleBtn.textContent = "View Technical JSON";

    // 2. Retrieve the log object
    const logItem = (window.currentAuditLogs || []).find(l => l.id === id) || null;
    
    // Parse previous and updated values
    let prevObj = null;
    let newObj = null;

    try {
        const rawPrev = logItem ? logItem.previous_value : (prevValEscaped ? unescapeHtml(prevValEscaped) : null);
        if (rawPrev && rawPrev !== "None") {
            prevObj = typeof rawPrev === "object" ? rawPrev : JSON.parse(rawPrev);
        }
    } catch (_) {
        prevObj = prevValEscaped ? unescapeHtml(prevValEscaped) : null;
    }

    try {
        const rawNew = logItem ? logItem.updated_value : (newValEscaped ? unescapeHtml(newValEscaped) : null);
        if (rawNew && rawNew !== "None") {
            newObj = typeof rawNew === "object" ? rawNew : JSON.parse(rawNew);
        }
    } catch (_) {
        newObj = newValEscaped ? unescapeHtml(newValEscaped) : null;
    }

    // Populate fallback raw JSON pre blocks
    const prevPre = document.getElementById("audit-prev-json");
    const newPre = document.getElementById("audit-new-json");
    if (prevPre) prevPre.textContent = prevObj ? (typeof prevObj === "object" ? JSON.stringify(prevObj, null, 4) : String(prevObj)) : "None (Create Record)";
    if (newPre) newPre.textContent = newObj ? (typeof newObj === "object" ? JSON.stringify(newObj, null, 4) : String(newObj)) : "None (Delete Record)";

    // Format metadata
    const eventType = logItem ? logItem.event_type : "AUDIT_EVENT";
    const tableName = logItem ? logItem.table_name : "database";
    const recordId = logItem ? logItem.record_id : id;
    const performedBy = logItem ? logItem.performed_by : "system";
    const timestampStr = logItem ? new Date(logItem.timestamp).toLocaleString() : new Date().toLocaleString();

    let friendlyEvent = eventType.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
    let friendlyTable = tableName.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
    if (tableName === "gtin_store") friendlyTable = "GTIN & Barcode Repository";
    if (tableName === "batches") friendlyTable = "Batch Production";
    if (tableName === "products") friendlyTable = "Product Master Catalog";
    if (tableName === "users") friendlyTable = "User Accounts";
    if (tableName === "roles") friendlyTable = "Roles & Permissions";

    // 3. Build Client-Friendly Text Layout
    let html = `
        <div class="audit-meta-grid" style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px;">
            <div>
                <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 700;">Action Performed</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #0f172a;">${friendlyEvent}</div>
            </div>
            <div>
                <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 700;">Target Section</div>
                <div style="font-size: 0.95rem; font-weight: 600; color: #0f2d59;">${friendlyTable}</div>
            </div>
            <div>
                <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 700;">Record Reference</div>
                <div style="font-size: 0.95rem; font-weight: 700; color: #1e293b;">${recordId}</div>
            </div>
            <div>
                <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 700;">Operator / User</div>
                <div style="font-size: 0.95rem; font-weight: 600; color: #0b6343;">${performedBy}</div>
            </div>
            <div>
                <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 700;">Logged At</div>
                <div style="font-size: 0.88rem; font-weight: 500; color: #475569;">${timestampStr}</div>
            </div>
        </div>
    `;

    // CASE 1: Both Previous & Updated exist (Record Update)
    if (prevObj && newObj && typeof prevObj === "object" && typeof newObj === "object") {
        const allKeys = Array.from(new Set([...Object.keys(prevObj), ...Object.keys(newObj)]));
        const changedKeys = [];

        allKeys.forEach(k => {
            if (JSON.stringify(prevObj[k]) !== JSON.stringify(newObj[k])) {
                changedKeys.push(k);
            }
        });

        if (changedKeys.length > 0) {
            html += `
                <div style="background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                        <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #d97706;"></span>
                        <strong style="color: #92400e; font-size: 0.92rem;">Summary of Changes (${changedKeys.length} field${changedKeys.length > 1 ? 's' : ''} modified):</strong>
                    </div>
                    <div style="overflow-x: auto; -webkit-overflow-scrolling: touch;">
                        <table class="table audit-changes-table" style="width: 100%; margin: 0; background: #ffffff; border-radius: 6px; overflow: hidden; font-size: 0.86rem; border: 1px solid #fed7aa;">
                            <thead>
                                <tr style="background: #fef3c7; color: #78350f; text-align: left;">
                                    <th style="padding: 9px 12px; width: 30%;">Field / Property</th>
                                    <th style="padding: 9px 12px; width: 35%;">Previous Value (Before)</th>
                                    <th style="padding: 9px 12px; width: 35%;">Updated Value (After)</th>
                                </tr>
                            </thead>
                            <tbody>
            `;

            changedKeys.forEach(k => {
                const label = formatAuditFieldLabel(k);
                const beforeVal = formatAuditValueAsText(k, prevObj[k]);
                const afterVal = formatAuditValueAsText(k, newObj[k]);

                html += `
                    <tr style="border-top: 1px solid #f3f4f6;">
                        <td style="font-weight: 600; color: #1e293b; padding: 10px 12px; vertical-align: top;">${label}</td>
                        <td style="color: #991b1b; background: #fff5f5; padding: 10px 12px; vertical-align: top;">${beforeVal}</td>
                        <td style="color: #166534; background: #f0fdf4; font-weight: 600; padding: 10px 12px; vertical-align: top;">${afterVal}</td>
                    </tr>
                `;
            });

            html += `
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }

        // Show full updated record details
        html += `
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
                <h4 style="margin: 0 0 12px; font-size: 0.88rem; color: #475569; text-transform: uppercase; letter-spacing: 0.04em;">Current Record State (All Values)</h4>
                <div class="audit-kv-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px;">
        `;

        Object.keys(newObj).forEach(k => {
            const label = formatAuditFieldLabel(k);
            const val = formatAuditValueAsText(k, newObj[k]);
            html += `
                <div class="audit-kv-item" style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #f1f5f9; padding: 6px 0; gap: 12px;">
                    <span class="audit-kv-label" style="color: #64748b; font-size: 0.84rem; flex-shrink: 0;">${label}:</span>
                    <span class="audit-kv-val" style="font-weight: 600; color: #0f172a; font-size: 0.86rem; text-align: right;">${val}</span>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;

    // CASE 2: New Record Created (prevObj is null or empty)
    } else if (newObj) {
        html += `
            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #16a34a;"></span>
                    <strong style="color: #166534; font-size: 0.92rem;">New Record Created</strong>
                    <span style="color: #15803d; font-size: 0.84rem;">— This entry was provisioned with the following details:</span>
                </div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
                <h4 style="margin: 0 0 12px; font-size: 0.88rem; color: #475569; text-transform: uppercase; letter-spacing: 0.04em;">Registered Properties</h4>
                <div class="audit-kv-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px;">
        `;

        if (typeof newObj === "object") {
            Object.keys(newObj).forEach(k => {
                const label = formatAuditFieldLabel(k);
                const val = formatAuditValueAsText(k, newObj[k]);
                html += `
                    <div class="audit-kv-item" style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #f1f5f9; padding: 6px 0; gap: 12px;">
                        <span class="audit-kv-label" style="color: #64748b; font-size: 0.84rem; flex-shrink: 0;">${label}:</span>
                        <span class="audit-kv-val" style="font-weight: 600; color: #0f172a; font-size: 0.86rem; text-align: right;">${val}</span>
                    </div>
                `;
            });
        } else {
            html += `<div style="font-size: 0.9rem; color: #0f172a;">${escapeHtml(String(newObj))}</div>`;
        }

        html += `
                </div>
            </div>
        `;

    // CASE 3: Record Deleted (newObj is null or empty)
    } else if (prevObj) {
        html += `
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #dc2626;"></span>
                    <strong style="color: #991b1b; font-size: 0.92rem;">Record Deleted</strong>
                    <span style="color: #b91c1c; font-size: 0.84rem;">— This entry was removed from the database tables.</span>
                </div>
            </div>
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px;">
                <h4 style="margin: 0 0 12px; font-size: 0.88rem; color: #475569; text-transform: uppercase; letter-spacing: 0.04em;">Archived Record Values Prior to Deletion</h4>
                <div class="audit-kv-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px;">
        `;

        if (typeof prevObj === "object") {
            Object.keys(prevObj).forEach(k => {
                const label = formatAuditFieldLabel(k);
                const val = formatAuditValueAsText(k, prevObj[k]);
                html += `
                    <div class="audit-kv-item" style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #f1f5f9; padding: 6px 0; gap: 12px;">
                        <span class="audit-kv-label" style="color: #64748b; font-size: 0.84rem; flex-shrink: 0;">${label}:</span>
                        <span class="audit-kv-val" style="font-weight: 600; color: #0f172a; font-size: 0.86rem; text-align: right;">${val}</span>
                    </div>
                `;
            });
        } else {
            html += `<div style="font-size: 0.9rem; color: #0f172a;">${escapeHtml(String(prevObj))}</div>`;
        }

        html += `
                </div>
            </div>
        `;
    } else {
        html += `
            <div style="padding: 24px; text-align: center; color: #64748b;">
                No additional record state was captured for this event.
            </div>
        `;
    }

    if (textSec) textSec.innerHTML = html;

    // Show modal
    const modal = document.getElementById("audit-details-modal");
    if (modal) modal.classList.remove("hidden");
};

// ----------------- SGTIN CSV Generator -----------------
async function generateSgtinCsv(e) {
    e.preventDefault();
    const gtin = document.getElementById("sgtin-gtin").value;
    const quantity = parseInt(document.getElementById("sgtin-qty").value, 10);
    const startSequence = parseInt(document.getElementById("sgtin-start-seq").value, 10);
    const submitButton = e.target.querySelector("button[type='submit']");
    const preview = document.getElementById("sgtin-preview");
    const message = document.getElementById("sgtin-message");

    preview.classList.add("hidden");

    if (!/^\d{14}$/.test(gtin)) {
        message.textContent = "GTIN must be exactly 14 digits.";
        message.className = "form-message error";
        return;
    }

    if (!quantity || quantity < 1 || quantity > 1000000) {
        message.textContent = "Quantity must be between 1 and 1000000.";
        message.className = "form-message error";
        return;
    }

    if (!startSequence || startSequence < 1) {
        message.textContent = "Start sequence must be 1 or higher.";
        message.className = "form-message error";
        return;
    }

    const length = parseInt(document.getElementById("sgtin-len").value, 10);
    const typeSelection = document.getElementById("sgtin-type").value;
    
    let alphabet = "23456789ABCDEFGHJKMNPQRSTVWXYZ";
    let requireAlpha = true;
    let requireNumeric = true;

    if (typeSelection === "numeric") {
        alphabet = "23456789";
        requireAlpha = false;
        requireNumeric = true;
    } else if (typeSelection === "alpha") {
        alphabet = "ABCDEFGHJKMNPQRSTVWXYZ";
        requireAlpha = true;
        requireNumeric = false;
    }

    message.textContent = "Generating CSV...";
    message.className = "form-message";
    submitButton.disabled = true;

    try {
        const res = await fetch("/api/v1/sgtin/generate-csv", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                gtin,
                quantity,
                start_sequence: startSequence,
                length,
                alphabet,
                require_alpha: requireAlpha,
                require_numeric: requireNumeric
            })
        });

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || "Failed to generate SGTIN CSV.");
        }

        const csvText = await res.text();
        const downloadName = `sgtin_${gtin}_${quantity}.csv`;
        
        showSgtinPreview(csvText, downloadName);
        message.textContent = "CSV Generation completed successfully!";
        message.className = "form-message success";
    } catch (err) {
        message.textContent = err.message;
        message.className = "form-message error";
    } finally {
        submitButton.disabled = false;
    }
}

function showSgtinPreview(csvText, downloadName) {
    const preview = document.getElementById("sgtin-preview");
    const tbody = document.getElementById("sgtin-preview-body");
    const downloadLink = document.getElementById("sgtin-download-link");

    if (!preview || !tbody || !downloadLink) return;

    tbody.innerHTML = "";

    // Parse CSV lines
    const lines = csvText.trim().split("\n");
    if (lines.length > 1) {
        // Skip header line (index 0), display data rows
        for (let i = 1; i < lines.length; i++) {
            const row = lines[i].split(",");
            if (row.length >= 4) {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>#${escapeHtml(row[0].trim())}</strong></td>
                    <td><code>${escapeHtml(row[1].trim())}</code></td>
                    <td><strong style="color: #0f5d7f; font-family: monospace;">${escapeHtml(row[2].trim())}</strong></td>
                    <td><code>${escapeHtml(row[3].trim())}</code></td>
                `;
                tbody.appendChild(tr);
            }
        }
    }

    // Prepare direct download link via Blob
    const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    downloadLink.href = url;
    downloadLink.setAttribute("download", downloadName || "sgtin_export.csv");

    preview.classList.remove("hidden");
}

// ----------------- Serial Validation & Lookup -----------------
let lastSearchedSerial = null;

async function performSerialLookup() {
    const inputVal = document.getElementById("search-serial").value.trim();
    const reportBox = document.getElementById("scan-report");
    const matrixBox = document.getElementById("matrix-box");
    
    if (!inputVal) return;

    reportBox.classList.add("hidden");
    if (matrixBox) matrixBox.classList.add("hidden");

    let serialToSearch = inputVal;
    let parsedGtin = "";
    let parsedLot = "";
    let parsedExpiry = "";

    // Check if it's a GS1 2D DataMatrix Simulation String
    // Expected format: (01)GTIN(21)SERIAL(10)LOT(17)EXPIRY
    if (inputVal.startsWith("(01)")) {
        const gtinMatch = inputVal.match(/\(01\)(\d{14})/);
        const serialMatch = inputVal.match(/\(21\)([A-Z0-9]+)/);
        const lotMatch = inputVal.match(/\(10\)([A-Z0-9-_]+)/);
        const expiryMatch = inputVal.match(/\(17\)(\d{6})/);

        if (gtinMatch && serialMatch) {
            parsedGtin = gtinMatch[1];
            serialToSearch = serialMatch[1];
            if (lotMatch) parsedLot = lotMatch[1];
            if (expiryMatch) parsedExpiry = expiryMatch[1];
        }
    }

    try {
        const res = await fetch(`/api/v1/serials/${encodeURIComponent(serialToSearch)}`);
        if (!res.ok) throw new Error("Serial number / Batch ID not found in database.");

        const serial = await res.json();
        lastSearchedSerial = serial;

        // Render Product & Packaging details
        const setElText = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val || "N/A";
        };

        setElText("rep-product-name", serial.product_name);
        setElText("rep-product", serial.product_id);
        setElText("rep-gtin", serial.gtin);
        setElText("rep-mfg", serial.manufacturer);
        setElText("rep-plant", serial.plant);
        setElText("rep-pkglevel", serial.packaging_level);
        setElText("rep-pkgsize", serial.packaging_size);

        const matchedGtin = registeredGtins.find(g => g.gtin === serial.gtin);
        const resolvedSerialType = serial.serial_no_type || (matchedGtin ? matchedGtin.serial_no_type : (serial.packaging_level === "Tertiary" ? "SSCC" : "SGTIN"));
        const resolvedPkgCategory = serial.packaging_category || (matchedGtin ? matchedGtin.packaging_category : (serial.packaging_level || "Primary"));
        setElText("rep-serial-type", `${resolvedSerialType} (${resolvedPkgCategory})`);

        // Render Batch details
        setElText("rep-batch-id", serial.batch_id);
        setElText("rep-lot", serial.batch_lot);
        setElText("rep-workorder", serial.work_order_no);
        setElText("rep-mfgdate", serial.mfg_date);
        setElText("rep-expiry", formatExpiryForDisplay(serial.expiry_date));
        setElText("rep-aggregated", serial.aggregated_batch ? "Yes" : "No");

        // Render Serial details
        setElText("rep-serial-num", serial.serial_number);
        setElText("rep-seq", `#${serial.sequence_number}`);
        
        // Full GS1 Element String
        const gtinVal = serial.gtin || "08901234567892";
        const gs1Full = `(01)${gtinVal}(21)${serial.serial_number}(17)${serial.expiry_date}(10)${serial.batch_lot}`;
        const gs1El = document.getElementById("rep-gs1-full");
        if (gs1El) gs1El.textContent = gs1Full;

        const badge = document.getElementById("rep-status-badge");
        if (badge) {
            badge.textContent = serial.status;
            badge.className = `badge status-badge badge-${serial.status.toLowerCase()}`;
        }

        // Render batch serials if present
        const batchSerialsPanel = document.getElementById("rep-batch-serials-panel");
        const batchSerialsBody = document.getElementById("rep-batch-serials-body");
        const batchSerialsCount = document.getElementById("rep-batch-serials-count");
        
        if (serial.batch_serials && serial.batch_serials.length > 0) {
            if (batchSerialsPanel) batchSerialsPanel.classList.remove("hidden");
            if (batchSerialsCount) batchSerialsCount.textContent = serial.batch_serials.length;
            if (batchSerialsBody) {
                batchSerialsBody.innerHTML = "";
                serial.batch_serials.forEach(bs => {
                    const tr = document.createElement("tr");
                    const isCurrent = bs.serial_number === serial.serial_number;
                    tr.style.backgroundColor = isCurrent ? "#eef6fa" : "transparent";
                    tr.innerHTML = `
                        <td><strong>#${bs.sequence_number}</strong></td>
                        <td><code style="color:#0f5d7f; font-weight:600;">${bs.serial_number}</code> ${isCurrent ? '<span class="badge badge-info" style="font-size:0.75rem; margin-left:4px;">Current Unit</span>' : ''}</td>
                        <td><span class="badge badge-${bs.status.toLowerCase()}">${bs.status}</span></td>
                        <td>
                            <button class="btn secondary-btn btn-sm" onclick="window.verifyDirectSerial('${bs.serial_number}')">Verify This Unit</button>
                        </td>
                    `;
                    batchSerialsBody.appendChild(tr);
                });
            }
        } else {
            if (batchSerialsPanel) batchSerialsPanel.classList.add("hidden");
        }

        // Render transition actions
        setupTransitionDropdownOptions(serial.status);

        // Render timeline
        renderTimeline(serial.history);
        reportBox.classList.remove("hidden");

        // Render simulated 2D DataMatrix barcode
        renderMatrixSimulation(
            serial.gtin || parsedGtin || "08901234567892",
            serial.serial_number,
            serial.batch_lot,
            serial.expiry_date
        );
    } catch (e) {
        alert(e.message);
    }
}

window.verifyDirectSerial = function(serialNum) {
    const input = document.getElementById("search-serial");
    if (input) {
        input.value = serialNum;
        switchView("view-verification");
        performSerialLookup();
    }
};

function setupTransitionDropdownOptions(status) {
    const dropdown = document.getElementById("target-state");
    dropdown.innerHTML = '<option value="" disabled selected>Choose transition</option>';
    
    const allowed = {
        "GENERATED": [
            { val: "ALLOCATED", label: "Allocate" },
            { val: "DECOMMISSIONED", label: "Decommission" }
        ],
        "ALLOCATED": [
            { val: "SHIPPED", label: "Ship" },
            { val: "DECOMMISSIONED", label: "Decommission" }
        ],
        "SHIPPED": [
            { val: "SOLD", label: "Mark sold" },
            { val: "DECOMMISSIONED", label: "Decommission" }
        ],
        "SOLD": [
            { val: "ACTIVATED", label: "Activate" },
            { val: "DECOMMISSIONED", label: "Decommission" }
        ],
        "ACTIVATED": [
            { val: "DECOMMISSIONED", label: "Decommission" }
        ],
        "DECOMMISSIONED": []
    };

    const options = allowed[status] || [];
    if (options.length === 0) {
        dropdown.disabled = true;
    } else {
        dropdown.disabled = false;
        options.forEach(opt => {
            const o = document.createElement("option");
            o.value = opt.val;
            o.textContent = opt.label;
            dropdown.appendChild(o);
        });
    }
}

async function performSerialTransition() {
    if (!lastSearchedSerial) return;
    const targetState = document.getElementById("target-state").value;
    if (!targetState) {
        alert("Please choose a transition state.");
        return;
    }

    try {
        const res = await fetch(`/api/v1/serials/${lastSearchedSerial.serial_number}/status`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                status: targetState,
                updated_by: "portal-operator",
                notes: `Manual verification state change to ${targetState}`
            })
        });

        const data = await res.json();
        if (res.ok) {
            alert(`Serial status successfully transitioned to ${targetState}`);
            performSerialLookup(); // refresh lookup report
            loadAuditLogs();
        } else {
            alert(`Error: ${data.detail || "Failed to transition status."}`);
        }
    } catch (e) {
        alert("Error: connection failed.");
    }
}

function renderTimeline(history) {
    const list = document.getElementById("lifecycle-timeline");
    list.innerHTML = "";
    history.forEach(item => {
        const li = document.createElement("li");
        const dateStr = new Date(item.timestamp).toLocaleString();
        li.innerHTML = `
            <div class="timeline-meta"><strong>${item.status}</strong> <small class="text-muted">${dateStr}</small></div>
            <div class="timeline-notes">${item.notes || ""} <small class="text-muted">by ${item.updated_by}</small></div>
        `;
        list.appendChild(li);
    });
}

function renderMatrixSimulation(gtin, serial, lot, expiry) {
    const canvas = document.getElementById("matrix-canvas");
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // Draw outer box
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 4;
    ctx.strokeRect(4, 4, canvas.width - 8, canvas.height - 8);

    // Draw simulated 2D DataMatrix grids (checkerboard block)
    ctx.fillStyle = "#ffffff";
    const size = 6;
    for (let x = 12; x < canvas.width - 12; x += size) {
        for (let y = 12; y < canvas.height - 12; y += size) {
            if ((Math.floor(x/size) + Math.floor(y/size)) % 2 === 0) {
                // mock noise block
                if (Math.random() > 0.3) {
                    ctx.fillRect(x, y, size - 1, size - 1);
                }
            }
        }
    }

    document.getElementById("bar-gtin").textContent = gtin;
    document.getElementById("bar-serial").textContent = serial;
    document.getElementById("bar-lot").textContent = lot;
    document.getElementById("bar-expiry").textContent = formatExpiryForDisplay(expiry);
    document.getElementById("matrix-box").classList.remove("hidden");
}

// ----------------- Helpers -----------------
function generateUUID() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function(c) {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

function formatExpiryForDisplay(val) {
    if (!val) return "N/A";
    const clean = String(val).trim();
    if (/^\d{6}$/.test(clean)) {
        return `20${clean.slice(0, 2)}-${clean.slice(2, 4)}-${clean.slice(4, 6)}`;
    }
    return clean;
}

function generateNewBatchIdempotencyKey() {
    const field = document.getElementById("batch-idempotency");
    if (field) field.value = generateUUID();
}

async function checkSystemHealth() {
    const dot = document.getElementById("db-status-dot");
    const text = document.getElementById("db-status-text");
    if (!dot || !text) return;

    try {
        const response = await fetch("/api/v1/health");
        if (!response.ok) throw new Error();
        dot.className = "status-indicator online";
        text.textContent = "System connected";
    } catch (e) {
        dot.className = "status-indicator offline";
        text.textContent = "Database offline";
    }
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function unescapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&amp;/g, "&")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&quot;/g, '"')
        .replace(/&#039;/g, "'");
}

// ============================================================
// Phase 2, 3, 4 Batch Execution Lifecycle Functions
// ============================================================

window.loadBatch = async function(batchId) {
    if (!confirm(`Dispatch batch '${batchId}' to Level 2 packaging line controller?`)) return;
    try {
        const res = await fetch(`/api/v1/batches/${batchId}/load`, {
            method: "POST"
        });
        const data = await res.json();
        if (res.ok) {
            alert(`Batch '${batchId}' successfully loaded to ${data.destination}.\nRecords Transmitted: ${data.total_records_transmitted}`);
            loadBatches();
            loadAuditLogs();
        } else {
            alert(`Load Batch Error: ${data.detail || "Failed to load batch."}`);
        }
    } catch (e) {
        alert("Error: connection failed while loading batch.");
    }
};

window.startBatch = async function(batchId) {
    if (!confirm(`Trigger START signal for batch '${batchId}' on Level 2 packaging line?`)) return;
    try {
        const res = await fetch(`/api/v1/batches/${batchId}/start`, {
            method: "POST"
        });
        const data = await res.json();
        if (res.ok) {
            alert(`Batch '${batchId}' started. Level 3 is now in execution monitoring state.`);
            loadBatches();
            loadAuditLogs();
        } else {
            alert(`Start Batch Error: ${data.detail || "Failed to start batch."}`);
        }
    } catch (e) {
        alert("Error: connection failed while starting batch.");
    }
};

window.openReconcileModal = function(batchId, totalCount) {
    const modal = document.getElementById("batch-reconcile-modal");
    if (!modal) return;
    
    document.getElementById("reconcile-batch-id").value = batchId;
    document.getElementById("reconcile-modal-subtitle").textContent = `Submit physical inspection counts for Batch: ${batchId}`;
    document.getElementById("reconcile-total-serials").textContent = totalCount;
    
    document.getElementById("reconcile-good-count").value = totalCount;
    document.getElementById("reconcile-rejected-count").value = 0;
    document.getElementById("reconcile-unused-count").value = 0;
    
    const msg = document.getElementById("reconcile-validation-msg");
    if (msg) {
        msg.textContent = "";
        msg.className = "form-message";
    }
    
    modal.classList.remove("hidden");
};

window.closeReconcileModal = function() {
    const modal = document.getElementById("batch-reconcile-modal");
    if (modal) modal.classList.add("hidden");
};

window.submitReconciliation = async function() {
    const batchId = document.getElementById("reconcile-batch-id").value;
    const totalCount = parseInt(document.getElementById("reconcile-total-serials").textContent || 0, 10);
    const good = parseInt(document.getElementById("reconcile-good-count").value || 0, 10);
    const rejected = parseInt(document.getElementById("reconcile-rejected-count").value || 0, 10);
    const unused = parseInt(document.getElementById("reconcile-unused-count").value || 0, 10);
    const msg = document.getElementById("reconcile-validation-msg");

    if (good < 0 || rejected < 0 || unused < 0) {
        msg.textContent = "Counts cannot be negative.";
        msg.className = "form-message error";
        return;
    }

    if ((good + rejected + unused) > totalCount) {
        msg.textContent = `Total reconciled items (${good + rejected + unused}) cannot exceed batch total (${totalCount}).`;
        msg.className = "form-message error";
        return;
    }

    msg.textContent = "Submitting reconciliation...";
    msg.className = "form-message";

    try {
        const res = await fetch(`/api/v1/batches/${batchId}/reconcile`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                good_count: good,
                rejected_count: rejected,
                unused_count: unused,
                operator_id: "operator-01"
            })
        });

        const data = await res.json();
        if (res.ok) {
            alert(`Reconciliation complete for '${batchId}'.\nGood Units (COMMITTED): ${data.good_count}\nRejected Units: ${data.rejected_count}\nUnused Returned: ${data.unused_count}`);
            window.closeReconcileModal();
            loadBatches();
            loadAuditLogs();
        } else {
            msg.textContent = `Error: ${data.detail || "Failed to reconcile batch."}`;
            msg.className = "form-message error";
        }
    } catch (e) {
        msg.textContent = "Error: connection failed.";
        msg.className = "form-message error";
    }
};

window.closeBatch = async function(batchId) {
    if (!confirm(`Are you sure you want to CLOSE and LOCK batch '${batchId}'?\nThis will finalize production metrics and prepare compliance XML.`)) return;
    try {
        const res = await fetch(`/api/v1/batches/${batchId}/close`, {
            method: "POST"
        });
        const data = await res.json();
        if (res.ok) {
            alert(`Batch '${batchId}' CLOSED and LOCKED.\nFinal Yield: ${data.yield_percentage}%\nStatus: CLOSED`);
            loadBatches();
            loadAuditLogs();
        } else {
            alert(`Close Batch Error: ${data.detail || "Failed to close batch."}`);
        }
    } catch (e) {
        alert("Error: connection failed while closing batch.");
    }
};

window.downloadXmlReport = function(batchId) {
    window.open(`/api/v1/batches/${batchId}/xml-report`, "_blank");
};

window.showBatchSummary = async function(batchId) {
    try {
        const res = await fetch(`/api/v1/batches/${batchId}/summary`);
        if (!res.ok) {
            const err = await res.json();
            alert(`Failed to load summary: ${err.detail || "Not found"}`);
            return;
        }
        const b = await res.json();
        
        const modal = document.getElementById("batch-summary-modal");
        const grid = document.getElementById("summary-metrics-grid");
        const lockBadge = document.getElementById("summary-lock-badge");
        const exportBtn = document.getElementById("btn-summary-export-xml");

        if (lockBadge) {
            lockBadge.textContent = b.is_locked ? "🔒 LOCKED & CLOSED" : b.status;
            lockBadge.className = `badge ${b.is_locked ? "badge-dark" : "badge-info"}`;
        }

        if (exportBtn) {
            exportBtn.onclick = () => window.downloadXmlReport(b.batch_id);
        }

        if (grid) {
            grid.innerHTML = `
                <div class="detail-row"><span>Batch ID</span> <strong>${b.batch_id}</strong></div>
                <div class="detail-row"><span>Product Code</span> <strong>${b.product_id}</strong></div>
                <div class="detail-row"><span>Lot Number</span> <strong>${b.batch_lot}</strong></div>
                <div class="detail-row"><span>Work Order</span> <strong>${b.work_order_no || 'N/A'}</strong></div>
                <div class="detail-row"><span>Packaging Line</span> <strong>${b.line_id || 'Line 01'}</strong></div>
                <div class="detail-row"><span>Transfer Protocol</span> <strong>${b.io_channel || 'DIRECT_API'}</strong></div>
                <div class="detail-row"><span>Requested Qty</span> <strong>${b.requested_quantity}</strong></div>
                <div class="detail-row"><span>Generated Qty</span> <strong>${b.generated_quantity}</strong></div>
                <div class="detail-row"><span>Primary / Sec / Ter Ratios</span> <strong>1 : ${b.secondary_ratio || 10} : ${b.tertiary_ratio || 10}</strong></div>
                <div class="detail-row"><span>Tier Breakdown</span> <strong>Pri: ${b.primary_quantity || 0} | Sec: ${b.secondary_quantity || 0} | Ter: ${b.tertiary_quantity || 0}</strong></div>
                <div class="detail-row" style="background:#e6f4ea;"><span>Reconciled Good</span> <strong style="color:#137333;">${b.reconciled_good_count !== null ? b.reconciled_good_count : 'N/A'}</strong></div>
                <div class="detail-row" style="background:#fce8e6;"><span>Reconciled Rejected</span> <strong style="color:#c5221f;">${b.reconciled_rejected_count !== null ? b.reconciled_rejected_count : 'N/A'}</strong></div>
                <div class="detail-row"><span>Unused Pool Units</span> <strong>${b.reconciled_unused_count !== null ? b.reconciled_unused_count : 'N/A'}</strong></div>
                <div class="detail-row" style="background:#e0f2fe;"><span>Yield Percentage</span> <strong style="color:#0369a1; font-size:1.1rem;">${b.yield_percentage !== null ? b.yield_percentage + '%' : 'Pending'}</strong></div>
            `;
        }

        if (modal) modal.classList.remove("hidden");
    } catch (e) {
        alert("Error loading batch summary.");
    }
};

window.closeSummaryModal = function() {
    const modal = document.getElementById("batch-summary-modal");
    if (modal) modal.classList.add("hidden");
};

// ============================================================
// Packaging Line Equipment & I/O Communication Route Handlers
// ============================================================

function resetLineForm() {
    const idInput = document.getElementById("line-id-input");
    const nameInput = document.getElementById("line-name-input");
    const plantInput = document.getElementById("line-plant-input");
    const protoSelect = document.getElementById("line-protocol-select");
    const apiInput = document.getElementById("line-api-endpoint");
    const msg = document.getElementById("line-form-msg");

    if (idInput) { idInput.value = ""; idInput.readOnly = false; }
    if (nameInput) nameInput.value = "";
    if (plantInput) plantInput.value = "TESTPLANT";
    if (protoSelect) protoSelect.value = "DIRECT_API";
    if (apiInput) apiInput.value = "";
    if (msg) { msg.textContent = ""; msg.className = "form-message"; }

    const activeRadios = document.getElementsByName("line-active");
    activeRadios.forEach(r => {
        if (r.value === "true") {
            r.checked = true;
            r.dispatchEvent(new Event("change"));
        } else {
            r.checked = false;
        }
    });
}

async function handleLineSaveSubmit(e) {
    e.preventDefault();
    const lineId = (document.getElementById("line-id-input")?.value || "").trim().toUpperCase();
    const lineName = (document.getElementById("line-name-input")?.value || "").trim();
    const plant = document.getElementById("line-plant-input")?.value || "TESTPLANT";
    const protocol = document.getElementById("line-protocol-select")?.value || "DIRECT_API";
    const apiEndpoint = (document.getElementById("line-api-endpoint")?.value || "").trim();
    const activeRadio = document.querySelector('input[name="line-active"]:checked');
    const isActive = activeRadio ? activeRadio.value === "true" : true;
    const msg = document.getElementById("line-form-msg");

    if (!lineId) return alert("Please enter Packaging Line ID (e.g. LINE-04).");
    if (!lineName) return alert("Please enter Packaging Line Name.");
    if (!plant) return alert("Please select Plant.");

    const payload = {
        line_id: lineId,
        name: lineName,
        plant: plant,
        io_protocol: protocol,
        api_endpoint: apiEndpoint || null,
        is_active: isActive
    };

    if (msg) {
        msg.textContent = "Saving packaging line...";
        msg.className = "form-message";
    }

    try {
        const res = await fetch("/api/v1/lines", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            if (msg) {
                msg.textContent = `Packaging Line ${data.line_id} registered successfully!`;
                msg.className = "form-message success";
            }
            await loadLines();
            loadAuditLogs();
            setTimeout(() => {
                switchView("view-line-list");
                resetLineForm();
            }, 1000);
        } else {
            if (msg) {
                msg.textContent = `Error: ${data.detail || "Failed to register line."}`;
                msg.className = "form-message error";
            }
        }
    } catch (err) {
        if (msg) {
            msg.textContent = `Error: ${err.message || "Connection failed."}`;
            msg.className = "form-message error";
        }
    }
}

function renderLineList(lines) {
    const tbody = document.getElementById("lines-list-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!lines || lines.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center">No packaging lines registered.</td></tr>`;
        return;
    }

    lines.forEach(l => {
        const tr = document.createElement("tr");
        const proto = l.io_protocol || l.protocol || "DIRECT_API";
        const lineName = l.name || l.line_name || l.line_id;

        let protoBadge = "badge-info";
        if (proto === "SHARED_FOLDER") protoBadge = "badge-warning";
        if (proto === "SFTP") protoBadge = "badge-primary";

        let dest = "N/A";
        if (proto === "DIRECT_API") {
            dest = l.api_endpoint || `http://127.0.0.1:8000/api/v1/l2/mock-controller/${l.line_id.toLowerCase()}`;
        } else if (proto === "SHARED_FOLDER") {
            dest = l.shared_folder_path || `l2_io/shared_folder/${l.line_id.toLowerCase()}`;
        } else if (proto === "SFTP") {
            dest = `${l.sftp_user || 'line_op'}@${l.sftp_host || 'sftp.local'}:${l.sftp_drop_folder || '/var/drop'}`;
        }

        tr.innerHTML = `
            <td><strong>${l.line_id}</strong></td>
            <td>${escapeHtml(lineName)}</td>
            <td>${escapeHtml(l.plant)}</td>
            <td><span class="badge ${protoBadge}">${proto}</span></td>
            <td><code style="font-size:0.8rem;">${escapeHtml(dest)}</code></td>
            <td><span class="badge ${l.is_active ? 'badge-success' : 'badge-secondary'}">${l.is_active ? 'ACTIVE' : 'INACTIVE'}</span></td>
            <td>
                <button class="btn secondary-btn btn-sm" onclick="window.configureLineIo('${l.line_id}')">Configure I/O</button>
                <button class="btn primary-btn btn-sm" onclick="window.testLineConnectivity('${l.line_id}')" style="margin-left: 4px;">Test Route</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function populateIoLineDropdown() {
    const sel = document.getElementById("io-select-line");
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = `<option value="" disabled selected>-- Select Packaging Line to Configure --</option>`;
    registeredLines.forEach(l => {
        const opt = document.createElement("option");
        opt.value = l.line_id;
        const lineName = l.name || l.line_name || l.line_id;
        opt.textContent = `${lineName} (${l.line_id}) - ${l.plant}`;
        sel.appendChild(opt);
    });
    if (currentVal) sel.value = currentVal;
}

window.configureLineIo = function(lineId) {
    switchView("view-line-io");
    populateIoForm(lineId);
};

function populateIoForm(preselectedLineId) {
    populateIoLineDropdown();
    const sel = document.getElementById("io-select-line");
    const targetLineId = preselectedLineId || (sel ? sel.value : null);
    if (!targetLineId) return;

    if (sel) sel.value = targetLineId;
    const line = registeredLines.find(l => l.line_id === targetLineId);
    if (!line) return;

    const proto = line.io_protocol || line.protocol || "DIRECT_API";
    const protoSel = document.getElementById("io-select-protocol");
    if (protoSel) protoSel.value = proto;

    toggleIoPanels(proto);

    // Populate paths & endpoints
    const sharedOut = document.getElementById("io-shared-path");
    const sharedIn = document.getElementById("io-shared-inbound");
    if (sharedOut) sharedOut.value = line.shared_folder_path || `l2_io/shared_folder/${line.line_id.toLowerCase()}/outbound`;
    if (sharedIn) sharedIn.value = line.sftp_inbound_folder || `l2_io/shared_folder/${line.line_id.toLowerCase()}/inbound`;

    const sftpHost = document.getElementById("io-sftp-host");
    const sftpPort = document.getElementById("io-sftp-port");
    const sftpUser = document.getElementById("io-sftp-user");
    const sftpPass = document.getElementById("io-sftp-pass");
    const sftpDrop = document.getElementById("io-sftp-drop");
    const sftpIn = document.getElementById("io-sftp-inbound");

    if (sftpHost) sftpHost.value = line.sftp_host || "sftp.pharma.local";
    if (sftpPort) sftpPort.value = line.sftp_port || 22;
    if (sftpUser) sftpUser.value = line.sftp_user || `${line.line_id.toLowerCase()}_op`;
    if (sftpPass) sftpPass.value = line.sftp_password || "";
    if (sftpDrop) sftpDrop.value = line.sftp_drop_folder || `/var/drop/${line.line_id.toLowerCase()}/outbound`;
    if (sftpIn) sftpIn.value = line.sftp_inbound_folder || `/var/drop/${line.line_id.toLowerCase()}/inbound`;

    const directApi = document.getElementById("io-direct-endpoint");
    if (directApi) directApi.value = line.api_endpoint || `http://127.0.0.1:8000/api/v1/l2/mock-controller/${line.line_id.toLowerCase()}`;

    const msg = document.getElementById("io-form-msg");
    if (msg) { msg.textContent = ""; msg.className = "form-message"; }
}

function toggleIoPanels(protocol) {
    const pShared = document.getElementById("io-panel-shared");
    const pSftp = document.getElementById("io-panel-sftp");
    const pDirect = document.getElementById("io-panel-direct");

    if (pShared) pShared.classList.add("hidden");
    if (pSftp) pSftp.classList.add("hidden");
    if (pDirect) pDirect.classList.add("hidden");

    if (protocol === "SHARED_FOLDER" && pShared) pShared.classList.remove("hidden");
    else if (protocol === "SFTP" && pSftp) pSftp.classList.remove("hidden");
    else if (pDirect) pDirect.classList.remove("hidden");
}

async function handleLineIoSaveSubmit(e) {
    e.preventDefault();
    const lineId = document.getElementById("io-select-line")?.value;
    if (!lineId) return alert("Please select a Packaging Line.");

    const protocol = document.getElementById("io-select-protocol")?.value || "DIRECT_API";
    const msg = document.getElementById("io-form-msg");

    const payload = {
        io_protocol: protocol
    };

    if (protocol === "DIRECT_API") {
        payload.api_endpoint = document.getElementById("io-direct-endpoint")?.value.trim() || null;
    } else if (protocol === "SHARED_FOLDER") {
        payload.shared_folder_path = document.getElementById("io-shared-path")?.value.trim() || null;
        payload.sftp_inbound_folder = document.getElementById("io-shared-inbound")?.value.trim() || null;
    } else if (protocol === "SFTP") {
        payload.sftp_host = document.getElementById("io-sftp-host")?.value.trim() || null;
        payload.sftp_port = parseInt(document.getElementById("io-sftp-port")?.value || "22", 10);
        payload.sftp_user = document.getElementById("io-sftp-user")?.value.trim() || null;
        payload.sftp_password = document.getElementById("io-sftp-pass")?.value || null;
        payload.sftp_drop_folder = document.getElementById("io-sftp-drop")?.value.trim() || null;
        payload.sftp_inbound_folder = document.getElementById("io-sftp-inbound")?.value.trim() || null;
    }

    if (msg) {
        msg.textContent = "Saving communication routes...";
        msg.className = "form-message";
    }

    try {
        const res = await fetch(`/api/v1/lines/${encodeURIComponent(lineId)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            if (msg) {
                msg.textContent = `I/O communication routes for Line ${lineId} saved successfully!`;
                msg.className = "form-message success";
            }
            await loadLines();
            loadAuditLogs();
        } else {
            if (msg) {
                msg.textContent = `Error: ${data.detail || "Failed to update line route."}`;
                msg.className = "form-message error";
            }
        }
    } catch (err) {
        if (msg) {
            msg.textContent = `Error: ${err.message || "Connection failed."}`;
            msg.className = "form-message error";
        }
    }
}

window.testLineConnectivity = async function(lineId) {
    if (!lineId) {
        const sel = document.getElementById("io-select-line");
        lineId = sel ? sel.value : null;
    }
    if (!lineId) return alert("Please select a Packaging Line to test connection.");

    const msg = document.getElementById("io-form-msg");
    if (msg) {
        msg.textContent = `Testing communication pathway for Line ${lineId}...`;
        msg.className = "form-message";
    }

    try {
        const res = await fetch(`/api/v1/lines/${encodeURIComponent(lineId)}/test-io`, {
            method: "POST"
        });
        const data = await res.json();
        if (res.ok) {
            alert(`[CONNECTION SUCCESS]\nLine: ${data.line_id} (${data.line_name})\nProtocol: ${data.io_protocol}\nStatus: ${data.status}\nMessage: ${data.message}`);
            if (msg) {
                msg.textContent = `Route Verified: ${data.message}`;
                msg.className = "form-message success";
            }
        } else {
            alert(`[CONNECTION ERROR]\n${data.detail || "Route unreachable."}`);
            if (msg) {
                msg.textContent = `Test Failed: ${data.detail || "Unreachable"}`;
                msg.className = "form-message error";
            }
        }
    } catch (err) {
        alert("Connection test error: server unreachable.");
    }
};

// ============================================================
// Code Pool Reservoir Functions (Import S/N)
// ============================================================

function setupPoolImportView() {
    const sel = document.getElementById("pool-import-product");
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = `<option value="" disabled selected>-- Select Product --</option>`;
    registeredProducts.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.product_id;
        opt.textContent = `${p.name} (${p.product_id})`;
        sel.appendChild(opt);
    });
    if (currentVal) sel.value = currentVal;
}

window.loadCodePoolStats = async function() {
    try {
        const res = await fetch("/api/v1/code-pool/stats");
        if (res.ok) {
            const data = await res.json();
            const totalEl = document.getElementById("pool-stat-total");
            const availEl = document.getElementById("pool-stat-available");
            const resEl = document.getElementById("pool-stat-reserved");
            const comEl = document.getElementById("pool-stat-committed");

            if (totalEl) totalEl.textContent = (data.total_codes || 0).toLocaleString();
            if (availEl) availEl.textContent = (data.available_codes || 0).toLocaleString();
            if (resEl) resEl.textContent = (data.reserved_codes || 0).toLocaleString();
            if (comEl) comEl.textContent = (data.committed_codes || 0).toLocaleString();
        }
    } catch (e) {
        console.error("Failed to load Code Pool reservoir stats", e);
    }
};

async function handleCodePoolImportSubmit(e) {
    e.preventDefault();
    const productId = document.getElementById("pool-import-product")?.value;
    const gtin = (document.getElementById("pool-import-gtin")?.value || "").trim();
    const tier = document.getElementById("pool-import-tier")?.value || "Primary";
    const rawSerials = document.getElementById("pool-import-serials")?.value || "";
    const msg = document.getElementById("pool-import-msg");

    if (!productId) return alert("Please select a Product.");
    if (!/^\d{14}$/.test(gtin)) return alert("Please enter a valid 14-digit GTIN.");

    const serialList = rawSerials
        .split(/[\r\n,]+/)
        .map(s => s.trim())
        .filter(s => s.length > 0);

    if (serialList.length === 0) {
        return alert("Please enter or upload at least 1 serial number.");
    }

    if (msg) {
        msg.textContent = `Importing ${serialList.length} serial numbers into reservoir...`;
        msg.className = "form-message";
    }

    const payload = {
        gtin: gtin,
        packaging_tier: tier,
        serials: serialList
    };

    try {
        const res = await fetch("/api/v1/code-pool/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok) {
            if (msg) {
                msg.textContent = `Successfully imported ${data.imported_count} serials (${data.skipped_duplicates} duplicate skipped).`;
                msg.className = "form-message success";
            }
            alert(`Code Pool Import Complete!\nImported: ${data.imported_count}\nDuplicates Skipped: ${data.skipped_duplicates}\nTarget GTIN: ${gtin}`);
            document.getElementById("pool-import-serials").value = "";
            const fileInput = document.getElementById("pool-import-file");
            if (fileInput) fileInput.value = "";
            window.loadCodePoolStats();
            loadAuditLogs();
        } else {
            if (msg) {
                msg.textContent = `Import error: ${data.detail || "Failed to import codes."}`;
                msg.className = "form-message error";
            }
        }
    } catch (err) {
        if (msg) {
            msg.textContent = `Error: ${err.message || "Connection failed."}`;
            msg.className = "form-message error";
        }
    }
}

// ============================================================
// Regulatory XML Report & Batch Summaries
// ============================================================

function setupXmlReportView() {
    const sel = document.getElementById("xml-select-batch");
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = `<option value="" disabled selected>-- Select Batch to Generate XML Report --</option>`;

    fetch("/api/v1/serialization/batches")
        .then(r => r.json())
        .then(batches => {
            batches.forEach(b => {
                const opt = document.createElement("option");
                opt.value = b.batch_id;
                opt.textContent = `${b.batch_id} - Lot: ${b.batch_lot} (${b.status})`;
                sel.appendChild(opt);
            });
            if (currentVal) sel.value = currentVal;
        })
        .catch(console.error);
}

async function previewSelectedXml() {
    const sel = document.getElementById("xml-select-batch");
    const batchId = sel ? sel.value : null;
    const viewer = document.getElementById("xml-viewer-code");
    if (!batchId) return alert("Please select a batch from the dropdown.");

    if (viewer) viewer.textContent = `Fetching EPCIS 1.2 XML report for batch ${batchId}...`;

    try {
        const res = await fetch(`/api/v1/batches/${encodeURIComponent(batchId)}/xml-report`);
        if (res.ok) {
            const xmlText = await res.text();
            if (viewer) viewer.textContent = xmlText;
        } else {
            const err = await res.text();
            if (viewer) viewer.textContent = `Error fetching XML report: ${err}`;
        }
    } catch (e) {
        if (viewer) viewer.textContent = `Connection error loading XML report: ${e.message}`;
    }
}

function downloadSelectedXml() {
    const sel = document.getElementById("xml-select-batch");
    const batchId = sel ? sel.value : null;
    if (!batchId) return alert("Please select a batch first.");
    window.downloadXmlReport(batchId);
}

window.loadBatchSummaryReport = async function() {
    const tbody = document.getElementById("report-summary-body");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="12" class="text-center">Loading batch summaries...</td></tr>`;

    try {
        const res = await fetch("/api/v1/reports/batch-summary");
        if (!res.ok) throw new Error("Failed to load batch summary");
        const list = await res.json();
        tbody.innerHTML = "";

        if (list.length === 0) {
            tbody.innerHTML = `<tr><td colspan="12" class="text-center">No batch records found.</td></tr>`;
            return;
        }

        list.forEach(b => {
            const tr = document.createElement("tr");
            let statusBadge = "badge-secondary";
            if (b.status === "CLOSED") statusBadge = "badge-dark";
            else if (b.status === "RECONCILED") statusBadge = "badge-primary";
            else if (b.status === "STARTED") statusBadge = "badge-warning";
            else if (b.status === "LOADED") statusBadge = "badge-info";

            const tierBreakdown = `${b.primary_quantity || 0} / ${b.secondary_quantity || 0} / ${b.tertiary_quantity || 0}`;

            tr.innerHTML = `
                <td><strong>${b.batch_id}</strong></td>
                <td>${b.product_id}</td>
                <td>${b.batch_lot}</td>
                <td>${b.line_id || 'Line 01'}</td>
                <td>${b.total_requested}</td>
                <td>${b.total_generated}</td>
                <td><small>${tierBreakdown}</small></td>
                <td><strong style="color: #137333;">${b.reconciled_good_count}</strong></td>
                <td><strong style="color: #c5221f;">${b.reconciled_rejected_count}</strong></td>
                <td>${b.reconciled_unused_count}</td>
                <td><strong style="color: #0369a1;">${b.yield_percentage !== null ? b.yield_percentage + '%' : 'Pending'}</strong></td>
                <td><span class="badge ${statusBadge}">${b.is_locked ? '🔒 CLOSED' : b.status}</span></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="12" class="text-center text-danger">Error loading batch summary report.</td></tr>`;
    }
};

function setupBatchReportDetailView() {
    const sel = document.getElementById("report-detail-select-batch");
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = `<option value="" disabled selected>-- Select Batch to Inspect Detailed Report --</option>`;

    fetch("/api/v1/serialization/batches")
        .then(r => r.json())
        .then(batches => {
            batches.forEach(b => {
                const opt = document.createElement("option");
                opt.value = b.batch_id;
                opt.textContent = `${b.batch_id} - Lot: ${b.batch_lot} (${b.status})`;
                sel.appendChild(opt);
            });
            if (currentVal) sel.value = currentVal;
        })
        .catch(console.error);
}

async function loadDetailedBatchReport() {
    const sel = document.getElementById("report-detail-select-batch");
    const batchId = sel ? sel.value : null;
    if (!batchId) return alert("Please select a batch from the dropdown.");

    const panel = document.getElementById("batch-detail-report-panel");
    const metricsDiv = document.getElementById("detail-report-metrics");
    const xmlBtn = document.getElementById("btn-detail-report-xml");

    try {
        const res = await fetch(`/api/v1/batches/${encodeURIComponent(batchId)}/summary`);
        if (!res.ok) {
            const err = await res.json();
            return alert(`Error: ${err.detail || "Batch not found"}`);
        }
        const b = await res.json();

        if (xmlBtn) {
            xmlBtn.onclick = () => window.downloadXmlReport(b.batch_id);
        }

        if (metricsDiv) {
            metricsDiv.innerHTML = `
                <div class="dashboard-grid mb-3">
                    <div class="dash-card">
                        <h4>Lifecycle Status</h4>
                        <p class="dash-metric" style="font-size: 1.25rem;">${b.is_locked ? '🔒 CLOSED & LOCKED' : b.status}</p>
                    </div>
                    <div class="dash-card">
                        <h4>Yield Percentage</h4>
                        <p class="dash-metric" style="color: #0369a1;">${b.yield_percentage !== null ? b.yield_percentage + '%' : 'Pending'}</p>
                    </div>
                    <div class="dash-card">
                        <h4>Good Units Released</h4>
                        <p class="dash-metric" style="color: #137333;">${b.reconciled_good_count !== null ? b.reconciled_good_count : 'Pending'}</p>
                    </div>
                    <div class="dash-card">
                        <h4>Defective / Scrapped</h4>
                        <p class="dash-metric" style="color: #c5221f;">${b.reconciled_rejected_count !== null ? b.reconciled_rejected_count : 0}</p>
                    </div>
                </div>

                <div class="table-container mt-3">
                    <table class="table">
                        <tbody>
                            <tr><th>Batch / Production Order</th><td><strong>${b.batch_id}</strong></td><th>Product Item Code</th><td>${b.product_id}</td></tr>
                            <tr><th>Lot / Control Number</th><td>${b.batch_lot}</td><th>Work Order Reference</th><td>${b.work_order_no || 'N/A'}</td></tr>
                            <tr><th>Packaging Line Identifier</th><td>${b.line_id || 'Line 01'}</td><th>I/O Transfer Route</th><td><code>${b.io_channel || 'DIRECT_API'}</code></td></tr>
                            <tr><th>Primary Requested Target</th><td>${b.requested_quantity} units</td><th>Total Serials Generated</th><td>${b.generated_quantity} units</td></tr>
                            <tr><th>Packaging Tier Distribution</th><td colspan="3">Primary: <strong>${b.primary_quantity || 0}</strong> | Secondary: <strong>${b.secondary_quantity || 0}</strong> | Tertiary: <strong>${b.tertiary_quantity || 0}</strong> (Ratio: 1 : ${b.secondary_ratio || 10} : ${b.tertiary_ratio || 10})</td></tr>
                            <tr><th>Unused Codes Returned to Reservoir</th><td>${b.reconciled_unused_count !== null ? b.reconciled_unused_count : 'N/A'}</td><th>Audit Certificate</th><td><span class="badge badge-success">✓ 21 CFR Part 11 Compliant</span></td></tr>
                        </tbody>
                    </table>
                </div>
            `;
        }

        if (panel) panel.classList.remove("hidden");
    } catch (e) {
        alert("Connection error loading detailed batch report.");
    }
}


