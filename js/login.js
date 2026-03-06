document.getElementById("loginBtn").onclick = function () {

  let role = document.getElementById("role").value;

  if (role === "teacher") {
    window.location.href = "dashboard.html?role=teacher";
  } else {
    window.location.href = "dashboard.html?role=student";
  }

};
