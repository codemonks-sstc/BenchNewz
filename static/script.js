document.addEventListener('click', async (e) => {
    const likeBtn = e.target.closest('.like');

    if (likeBtn) {

        const post = likeBtn.closest('[data-post-id]');
        const postId = post?.dataset.postId;
        const likeCountEl = post?.querySelector('.like-count');

        console.log("POST:", post);
        console.log("POST ID:", postId);

        if (!postId) {
            console.error("Post ID missing ❌");
            return;
        }

        const res = await fetch(`/post/${postId}/react`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ type: 'like' })
        });

        const data = await res.json();

        // UI update
        if (data.status === 'added') {
            likeBtn.textContent = 'favorite';
            likeBtn.classList.add('liked');
        } else {
            likeBtn.textContent = 'heart_plus';
            likeBtn.classList.remove('liked');
        }

        if (data.likes !== undefined && likeCountEl) {
            if (data.likes == 1){
                likeCountEl.textContent = data.likes + ' Like';
            }
            else {
                likeCountEl.textContent = data.likes + ' Likes';
            }
        }
    }
});

document.addEventListener('click', async (e) => {
    const reportBtn = e.target.closest('.report');
    if (!reportBtn) return;

    const post = reportBtn.closest('[data-post-id]');
    const postId = post?.dataset.postId;

    if (!postId) {
        console.error("Post ID missing ❌");
        return;
    }

    const confirmReport = confirm("Are you sure you want to report this post?");

    if (!confirmReport) return;

    const res = await fetch(`/post/${postId}/report`, {
        method: 'POST'
    });

    const data = await res.json();

    if (data.status === 'reported') {
        reportBtn.style.color = 'red';

        // Optional UX improvement
        post.style.opacity = "0.6";
    }

    if (data.status === 'already_reported') {
        console.warn("Already reported");
    }
});


document.addEventListener('DOMContentLoaded', () => {

    function toggleDarkMode(isEnabled) {
        document.body.classList.toggle("dark-mode", isEnabled);
        localStorage.setItem("darkMode", isEnabled);
        document.getElementById("dark-mode").checked = isEnabled;
    }

    toggleDarkMode(localStorage.getItem("darkMode") === "true");

    document.getElementById('dark-mode').addEventListener('click', () => {
        const isDark = !document.body.classList.contains("dark-mode");
        toggleDarkMode(isDark);
    });

    const errorBox = document.querySelector('.error-box');

    if (errorBox && errorBox.textContent.trim() !== "") {
        alert(errorBox.textContent.trim());
        errorBox.style.display = "none";
    }

});


function alt() {
        alert('Only reporters can make posts. To post, please change your role from the profile section.');
}

function toggleContent(btn) {
    const mark = btn.closest('.mark');
    const expanded = mark.dataset.expanded === 'true';

    mark.innerHTML = (expanded ? mark.dataset.short : mark.dataset.full);

    const newBtn = document.createElement('span');
    newBtn.className = 'show-more-btn';
    newBtn.textContent = expanded ? 'Show more' : 'Show less';
    newBtn.onclick = () => toggleContent(newBtn);
    mark.appendChild(newBtn);

    mark.dataset.expanded = String(!expanded);
}

// collapse on outside click
document.addEventListener('click', function (e) {
    document.querySelectorAll('.mark[data-expanded="true"]').forEach(mark => {
        if (!mark.contains(e.target)) {
            mark.innerHTML = mark.dataset.short;
            const btn = document.createElement('span');
            btn.className = 'show-more-btn';
            btn.textContent = 'Show more';
            btn.onclick = () => toggleContent(btn);
            mark.appendChild(btn);
            mark.dataset.expanded = 'false';
        }
    });
});