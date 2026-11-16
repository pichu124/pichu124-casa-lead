// Ẩn / hiện ô theo lựa chọn khác (data-hien-khi="ten=giá trị|giá trị", data-an-khi tương tự).
// Chỉ để gọn màn hình: máy chủ vẫn tự kiểm và xoá giá trị ở ô không có nghĩa.
(function () {
  function giaTri(ten) {
    var o = document.querySelectorAll('[name="' + ten + '"]');
    for (var i = 0; i < o.length; i++) {
      if (o[i].type === 'radio') { if (o[i].checked) return o[i].value; }
      else return o[i].value;
    }
    return '';
  }
  function khop(dk) {
    var p = dk.split('='), ds = p[1].split('|');
    return ds.indexOf(giaTri(p[0])) >= 0;
  }
  function capNhat() {
    document.querySelectorAll('[data-hien-khi]').forEach(function (el) { el.hidden = !khop(el.dataset.hienKhi); });
    document.querySelectorAll('[data-an-khi]').forEach(function (el) { el.hidden = khop(el.dataset.anKhi); });
  }
  document.addEventListener('change', capNhat);
  document.addEventListener('DOMContentLoaded', capNhat);
})();
