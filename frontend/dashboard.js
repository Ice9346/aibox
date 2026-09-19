// ============================================================
// Learning Box - Dashboard
// dashboard.js
// ============================================================

document.addEventListener("DOMContentLoaded", function () {
  // ตรวจสอบว่า Login อยู่หรือไม่
  const currentUser = getCurrentUser();

  if (!currentUser) {
    window.location.href = "login.html";
    return;
  }

  // แสดงข้อมูลผู้ใช้
  displayCurrentUser();
});

// ============================================================
// แสดงข้อมูลผู้ใช้ที่ Login อยู่
// ============================================================

function displayCurrentUser() {
  const user = getCurrentUser();

  if (!user) {
    return;
  }

  const nameElement = document.getElementById("currentUserName");
  const roleElement = document.getElementById("currentUserInfo");

  if (nameElement) {
    nameElement.textContent = `${user.firstName} ${user.lastName}`;
  }

  if (roleElement) {
    const role = user.role || "ผู้สอน";
    const faculty = user.faculty || "";

    roleElement.textContent = faculty ? `${role} · ${faculty}` : role;
  }
}

// ============================================================
// Logout
// ============================================================

function handleLogout() {
  logoutUser();

  window.location.href = "login.html";
}
