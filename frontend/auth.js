// ============================================================
// Learning Box - Authentication
// auth.js
// ============================================================

// ชื่อที่ใช้เก็บข้อมูลผู้ใช้ใน Browser
const USERS_KEY = "learningBoxUsers";
const CURRENT_USER_KEY = "learningBoxCurrentUser";

// ------------------------------------------------------------
// ดึงรายชื่อผู้ใช้ทั้งหมด
// ------------------------------------------------------------
function getUsers() {
  try {
    const users = localStorage.getItem(USERS_KEY);
    return users ? JSON.parse(users) : [];
  } catch (error) {
    console.error("ไม่สามารถอ่านข้อมูลผู้ใช้ได้:", error);
    return [];
  }
}

// ------------------------------------------------------------
// บันทึกรายชื่อผู้ใช้ทั้งหมด
// ------------------------------------------------------------
function saveUsers(users) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

// ------------------------------------------------------------
// สมัครสมาชิก
// ------------------------------------------------------------
function registerUser(firstName, lastName, email, password) {
  const users = getUsers();

  const cleanFirstName = firstName.trim();
  const cleanLastName = lastName.trim();
  const cleanEmail = email.trim().toLowerCase();

  // ตรวจสอบข้อมูลเบื้องต้น
  if (!cleanFirstName || !cleanLastName || !cleanEmail || !password) {
    return {
      success: false,
      message: "กรุณากรอกข้อมูลให้ครบทุกช่อง",
    };
  }

  // ตรวจสอบ Email ซ้ำ
  const existingUser = users.find((user) => user.email === cleanEmail);

  if (existingUser) {
    return {
      success: false,
      message: "อีเมลนี้ถูกใช้งานแล้ว",
    };
  }

  // สร้าง User ใหม่
  const newUser = {
    id: Date.now().toString(),
    firstName: cleanFirstName,
    lastName: cleanLastName,
    email: cleanEmail,
    password: password,
    role: "ผู้สอน",
    faculty: "Faculty of Science",
  };

  users.push(newUser);
  saveUsers(users);

  return {
    success: true,
    message: "สมัครสมาชิกสำเร็จ",
    user: newUser,
  };
}

// ------------------------------------------------------------
// Login
// ------------------------------------------------------------
function loginUser(email, password) {
  const users = getUsers();

  const cleanEmail = email.trim().toLowerCase();

  const user = users.find(
    (user) => user.email === cleanEmail && user.password === password,
  );

  if (!user) {
    return {
      success: false,
      message: "อีเมลหรือรหัสผ่านไม่ถูกต้อง",
    };
  }

  // ข้อมูลที่ใช้ระบุว่าใครกำลัง Login
  const currentUser = {
    id: user.id,
    firstName: user.firstName,
    lastName: user.lastName,
    email: user.email,
    role: user.role,
    faculty: user.faculty,
  };

  localStorage.setItem(CURRENT_USER_KEY, JSON.stringify(currentUser));

  return {
    success: true,
    message: "เข้าสู่ระบบสำเร็จ",
    user: currentUser,
  };
}

// ------------------------------------------------------------
// ดึงข้อมูลคนที่กำลัง Login
// ------------------------------------------------------------
function getCurrentUser() {
  try {
    const user = localStorage.getItem(CURRENT_USER_KEY);

    return user ? JSON.parse(user) : null;
  } catch (error) {
    console.error("ไม่สามารถอ่านข้อมูลผู้ใช้ปัจจุบันได้:", error);
    return null;
  }
}

// ------------------------------------------------------------
// ตรวจสอบว่ามีคน Login อยู่หรือไม่
// ------------------------------------------------------------
function isLoggedIn() {
  return getCurrentUser() !== null;
}

// ------------------------------------------------------------
// Logout
// ------------------------------------------------------------
function logoutUser() {
  localStorage.removeItem(CURRENT_USER_KEY);
}

// ------------------------------------------------------------
// ชื่อเต็มของผู้ใช้
// ------------------------------------------------------------
function getFullName(user) {
  if (!user) {
    return "";
  }

  return `${user.firstName} ${user.lastName}`.trim();
}

// ------------------------------------------------------------
// สำหรับตรวจสอบจาก Console
// ------------------------------------------------------------
console.log("Learning Box auth.js loaded");
