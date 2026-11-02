# Remote Employee Access & Security Policy

This guide defines how Directors and Purchase staff securely access the StockGuard application from outside the corporate office network.

---

## 1. Remote Access Architecture Options

Depending on your organization's IT infrastructure, use one of the following recommended methods:

### Option A: Cloudflare Zero Trust / Access Tunnel (Recommended)
- The application is published behind **Cloudflare Access**.
- Employees authenticate through their Microsoft 365 / Entra ID or Google Workspace accounts.
- Multi-Factor Authentication (MFA / 2FA) is strictly enforced before web traffic reaches the app.
- No public open ports on the hosting server.

### Option B: Corporate Virtual Private Network (VPN)
- The application is hosted internally or on a private cloud subnet.
- Remote staff connect via corporate WireGuard, OpenVPN, or Fortinet / Cisco AnyConnect VPN.
- Only devices authenticated through the VPN subnet can resolve the internal application URL.

---

## 2. Authentication & Session Security Controls

1. **Role-Based Authorization (RBAC)**:
   - Every protected API endpoint enforces role membership on the backend.
   - Directors have full reporting and overview visibility.
   - Purchase Team members have stock balance and movement lookup capabilities without admin configuration access.
   - Stock quantities remain strictly read-only for all employees; updates occur exclusively through Excel sync.

2. **Session Lifetimes & Inactivity**:
   - Web tokens expire after 12 hours of session activity.
   - Inactive tokens are revoked automatically.

3. **No Shared Accounts**:
   - Each employee must be provisioned an individual named account (`firstname.lastname@company.com`).
   - Group logins (e.g. `purchasing@company.com` shared by 5 people) are prohibited to maintain audit trail integrity.

4. **Security Audit Trails**:
   - Every login event, report export, and administrative action is logged to the PostgreSQL `audit_logs` table with user email, timestamp, and client IP address.

---

## 3. Remote Device Guidelines for Employees

- Employees accessing stock records from home or mobile devices must use corporate-managed or PIN-protected devices.
- Do not download or store unencrypted CSV/Excel stock valuation reports on public or unmonitored devices.
- Immediately report lost or stolen devices to IT administrators so that session tokens and accounts can be deactivated.
