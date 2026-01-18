const EMOJIS = ["😄","🔥","💛","✨","🌀","🎯","🚀","🌟","😎","🍋","🧡","😂","💥","🎉","🧸","🪩","💫","🧩","🕺","🎵"];
const layer = document.getElementById("emoji-layer");

function rand(min, max) {
  return Math.random() * (max - min) + min;
}

function spawnEmoji() {
  const e = document.createElement("div");
  e.className = "emoji";
  e.textContent = EMOJIS[Math.floor(Math.random() * EMOJIS.length)];

  const w = window.innerWidth;
  const h = window.innerHeight;

  // start from edges
  const side = Math.floor(Math.random() * 4);
  let x = 0, y = 0;
  if (side === 0) { x = rand(0, w); y = -30; }       // top
  if (side === 1) { x = w + 30; y = rand(0, h); }   // right
  if (side === 2) { x = rand(0, w); y = h + 30; }   // bottom
  if (side === 3) { x = -30; y = rand(0, h); }      // left

  e.style.left = `${x}px`;
  e.style.top = `${y}px`;

  const dx = rand(-w * 0.6, w * 0.6);
  const dy = rand(-h * 0.6, h * 0.6);
  e.style.setProperty("--dx", `${dx}px`);
  e.style.setProperty("--dy", `${dy}px`);

  const dur = rand(6, 14);
  e.style.animationDuration = `${dur}s`;

  layer.appendChild(e);
  setTimeout(() => e.remove(), (dur + 0.5) * 1000);
}

for (let i = 0; i < 35; i++) setTimeout(spawnEmoji, i * 120);
setInterval(spawnEmoji, 200);

// UI
const fbUrl = document.getElementById("fbUrl");
const goBtn = document.getElementById("goBtn");
const statusBox = document.getElementById("status");
const results = document.getElementById("results");

const profileBlock = document.getElementById("profileBlock");
const coverBlock = document.getElementById("coverBlock");
const photoList = document.getElementById("photoList");

function setStatus(msg, ok = true) {
  statusBox.textContent = msg;
  statusBox.style.color = ok ? "#0b3d0b" : "#7a0b0b";
}

function fileNameFromUrl(url, fallback) {
  try {
    const u = new URL(url);
    const last = (u.pathname.split("/").filter(Boolean).pop() || fallback);
    return last.includes(".") ? last : `${fallback}.jpg`;
  } catch {
    return `${fallback}.jpg`;
  }
}

function imageWithButtons(urlStd, urlHd, labelBase) {
  const best = urlHd || urlStd;
  if (!best) return "<p class=\"muted\">Not found</p>";

  const stdBtn = urlStd ? `<a class="btn" href="${urlStd}" target="_blank" rel="noopener" download="${fileNameFromUrl(urlStd, labelBase)}">Download Standard</a>` : "";
  const hdBtn  = urlHd  ? `<a class="btn" href="${urlHd}" target="_blank" rel="noopener" download="${fileNameFromUrl(urlHd, labelBase + "_hd")}">Download HD</a>` : "";

  return `
    <img src="${best}" alt="${labelBase}" loading="lazy" />
    <div class="downloadRow">
      ${stdBtn}
      ${hdBtn}
    </div>
  `;
}

function photoItem(url, idx) {
  const name = fileNameFromUrl(url, `photo_${idx + 1}`);
  return `
    <div class="photoItem">
      <img src="${url}" alt="photo ${idx + 1}" loading="lazy" />
      <a class="miniBtn" href="${url}" target="_blank" rel="noopener" download="${name}">Download</a>
    </div>
  `;
}

async function fetchPics() {
  const url = fbUrl.value.trim();
  if (!url) {
    setStatus("Facebook link paste করো 🙂", false);
    return;
  }

  setStatus("Loading... 😄");
  goBtn.disabled = true;
  results.classList.add("hidden");

  profileBlock.innerHTML = "";
  coverBlock.innerHTML = "";
  photoList.innerHTML = "";

  try {
    const res = await fetch(`/api/all?url=${encodeURIComponent(url)}`);
    const data = await res.json();

    if (!res.ok || !data.success) {
      setStatus(data.message || "Failed!", false);
      goBtn.disabled = false;
      return;
    }

    setStatus(`Done ✅ Total found: ${data.total_count}`);

    const pStd = data.profile_picture?.standard;
    const pHd = data.profile_picture?.hd;
    profileBlock.innerHTML = imageWithButtons(pStd, pHd, "profile");

    const cStd = data.cover_photo?.standard;
    const cHd = data.cover_photo?.hd;
    coverBlock.innerHTML = imageWithButtons(cStd, cHd, "cover");

    const photos = data.photos || [];
    photoList.innerHTML = photos.map((u, i) => photoItem(u, i)).join("");

    results.classList.remove("hidden");

  } catch (err) {
    setStatus("Error: " + err.message, false);
  } finally {
    goBtn.disabled = false;
  }
}

goBtn.addEventListener("click", fetchPics);
fbUrl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") fetchPics();
});
