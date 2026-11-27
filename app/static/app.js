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


// Ô "Chưa rõ" của Cơ sở quan tâm: tích Chưa rõ thì bỏ các cơ sở, tích một cơ sở thì bỏ Chưa rõ.
document.addEventListener('change', function (e) {
  var o = e.target, khung = o.closest && o.closest('[data-loai-tru]');
  if (!khung || o.type !== 'checkbox' || !o.checked) return;
  khung.querySelectorAll('input[type=checkbox]').forEach(function (x) {
    if (x !== o && (o.value === 'Chưa rõ' || x.value === 'Chưa rõ')) x.checked = false;
  });
});


// Bấm ▲ ▼ / Bỏ ở Cài đặt → Danh mục: trang tải lại vẫn ở chỗ đang làm, không nhảy lên đầu trang.
// Chỉ nhớ trong vài giây và chỉ cho đúng trang đó; bấm Huỷ ở hộp xác nhận (defaultPrevented) thì không nhớ.
(function () {
  var KHOA = 'giu-cuon';
  document.addEventListener('submit', function (e) {
    if (e.defaultPrevented || !e.target.closest('.ds-danh-muc')) return;
    try { sessionStorage.setItem(KHOA, JSON.stringify({ trang: location.pathname, y: scrollY, luc: Date.now() })); } catch (_) {}
  });
  var luu = null;
  try { luu = JSON.parse(sessionStorage.getItem(KHOA) || 'null'); sessionStorage.removeItem(KHOA); } catch (_) {}
  if (luu && luu.trang === location.pathname && Date.now() - luu.luc < 15000) {
    var cuon = function () { scrollTo(0, luu.y); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', cuon); else cuon();
  }
})();
