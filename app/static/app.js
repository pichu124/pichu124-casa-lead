// Ẩn / hiện ô theo lựa chọn khác (data-hien-khi="ten=giá trị|giá trị", data-an-khi tương tự).
// Chỉ để gọn màn hình: máy chủ vẫn tự kiểm và xoá giá trị ở ô không có nghĩa.
(function () {
  // Các giá trị đang chọn của ô `ten`: radio / checkbox lấy các ô được tích, ô khác lấy giá trị.
  function giaTri(ten) {
    var o = document.querySelectorAll('[name="' + ten + '"]'), kq = [];
    for (var i = 0; i < o.length; i++) {
      if (o[i].type === 'radio' || o[i].type === 'checkbox') { if (o[i].checked) kq.push(o[i].value); }
      else kq.push(o[i].value);
    }
    return kq.length ? kq : [''];
  }
  function khop(dk) {
    var p = dk.split('='), ds = p[1].split('|'), dang = giaTri(p[0]);
    for (var i = 0; i < dang.length; i++) { if (ds.indexOf(dang[i]) >= 0) return true; }
    return false;
  }
  function capNhat() {
    document.querySelectorAll('[data-hien-khi]').forEach(function (el) { el.hidden = !khop(el.dataset.hienKhi); });
    document.querySelectorAll('[data-an-khi]').forEach(function (el) { el.hidden = khop(el.dataset.anKhi); });
  }
  document.addEventListener('change', capNhat);
  document.addEventListener('DOMContentLoaded', capNhat);
})();

