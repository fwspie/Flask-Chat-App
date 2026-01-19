let currentUser = null;
let currentRoom = null;
let pollInterval;
let displayedMessageIds = new Set();

async function getCurrentUser() {
    try {
        const response = await fetch('/api/user');
        if (response.ok) {
            const data = await response.json();
            currentUser = data;
            document.getElementById('currentUsername').textContent = `${data.username}`;
            await loadRooms();
        } else {
            window.location.href = '/';
        }
    } catch (error) {
        console.error('Error fetching user:', error);
        window.location.href = '/';
    }
}

async function loadRooms() {
    try {
        const response = await fetch('/api/rooms');
        if (response.ok) {
            const userRooms = await response.json();
            
            const publicResponse = await fetch('/api/rooms/public');
            const publicRooms = publicResponse.ok ? await publicResponse.json() : [];

            displayRooms(userRooms, publicRooms);

            const publicRoom = publicRooms.find(r => r.name === 'Public Room');
            if (publicRoom && !userRooms.find(r => r.id === publicRoom.id)) {
                await joinRoom(publicRoom.id);
                userRooms.push(publicRoom);
            }

            if (userRooms.length > 0) {
                const publicRoomData = userRooms.find(r => r.type === 'public');
                if (publicRoomData) {
                    selectRoom(publicRoomData.id);
                }
            }
        }
    } catch (error) {
        console.error('Error loading rooms:', error);
    }
}

function displayRooms(userRooms, publicRooms) {
    const publicRoomsList = document.getElementById('publicRoomsList');
    publicRoomsList.innerHTML = '';

    publicRooms.forEach(room => {
        const isJoined = userRooms.find(r => r.id === room.id);
        if (isJoined) {
            const roomEl = document.createElement('div');
            roomEl.className = 'room-item';
            roomEl.textContent = room.name;
            roomEl.onclick = () => selectRoom(room.id);
            publicRoomsList.appendChild(roomEl);
        }
    });

    const contactsList = document.getElementById('contactsList');
    contactsList.innerHTML = '';

    const privateRooms = userRooms.filter(r => r.type === 'private');
    privateRooms.forEach(room => {
        const roomEl = document.createElement('div');
        roomEl.className = 'room-item';
        const roomName = room.name.replace(`${currentUser.username}-`, '').replace(currentUser.username, '');
        roomEl.textContent = roomName || room.name;
        roomEl.onclick = () => selectRoom(room.id);
        contactsList.appendChild(roomEl);
    });
}

async function selectRoom(roomId) {
    currentRoom = roomId;
    displayedMessageIds.clear();
    
    // Clear all messages from DOM to prevent duplication
    const container = document.getElementById('messagesContainer');
    if (container) {
        container.innerHTML = '';
    }

    document.querySelectorAll('.room-item').forEach(el => {
        el.classList.remove('active');
    });
    if (event.target) {
        event.target.classList.add('active');
    }

    // Close sidebar on mobile after selecting room
    const sidebar = document.querySelector('.sidebar');
    const roomsList = document.querySelector('.rooms-list');
    const sidebarFooter = document.querySelector('.sidebar-footer');
    
    if (window.innerWidth <= 768) {
        sidebar.classList.remove('open');
        roomsList.classList.remove('show');
        sidebarFooter.classList.remove('show');
    }

    await loadMessages();
}

async function joinRoom(roomId) {
    try {
        await fetch(`/api/rooms/${roomId}/join`, {
            method: 'POST'
        });
    } catch (error) {
        console.error('Error joining room:', error);
    }
}

async function loadMessages() {
    if (!currentRoom) return;

    try {
        const response = await fetch(`/api/rooms/${currentRoom}/messages`);
        if (response.ok) {
            const messages = await response.json();
            displayMessages(messages);
        }
    } catch (error) {
        console.error('Error loading messages:', error);
    }
}

function displayMessages(messages) {
    const container = document.getElementById('messagesContainer');
    const wasAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 10;

    messages.forEach(msg => {
        if (!displayedMessageIds.has(msg.id)) {
            displayedMessageIds.add(msg.id);

            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${msg.user_id === currentUser.user_id ? 'own' : 'other'}`;

            const headerDiv = document.createElement('div');
            headerDiv.className = 'message-header';
            headerDiv.textContent = msg.username;

            if (msg.image_url) {
                const imageDiv = document.createElement('div');
                imageDiv.className = 'message-image';
                const img = document.createElement('img');
                img.src = msg.image_url;
                img.alt = 'Shared image';
                img.addEventListener('click', () => openImageModal(msg.image_url));
                imageDiv.appendChild(img);
                messageDiv.appendChild(imageDiv);
            }

            if (msg.content) {
                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';
                contentDiv.textContent = msg.content;
                messageDiv.appendChild(contentDiv);
            }

            const timeDiv = document.createElement('div');
            timeDiv.className = 'message-time';
            timeDiv.textContent = msg.created_at;

            messageDiv.insertBefore(headerDiv, messageDiv.firstChild);
            messageDiv.appendChild(timeDiv);

            container.appendChild(messageDiv);
        }
    });

    // Auto-scroll to bottom if was already at bottom
    if (wasAtBottom) {
        container.scrollTop = container.scrollHeight;
    }
}

async function sendMessage(event) {
    event.preventDefault();
    if (!currentRoom) return;

    const input = document.getElementById('messageInput');
    const fileInput = document.getElementById('imageInput');
    const content = input.value.trim();
    const file = fileInput.files[0];

    if (!content && !file) return;

    if (file && file.size > 10 * 1024 * 1024) {
        alert('File size exceeds 10MB limit');
        return;
    }

    try {
        const formData = new FormData();
        formData.append('content', content);
        if (file) {
            formData.append('image', file);
        }

        const response = await fetch(`/api/rooms/${currentRoom}/messages`, {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            input.value = '';
            fileInput.value = '';
            updateImagePreview();
            await loadMessages();
        } else {
            const data = await response.json();
            alert(data.error || 'Failed to send message');
        }
    } catch (error) {
        console.error('Error sending message:', error);
        alert('An error occurred while sending the message');
    }
}

async function logout() {
    try {
        await fetch('/api/logout', { method: 'POST' });
        window.location.href = '/';
    } catch (error) {
        console.error('Error logging out:', error);
    }
}

function updateImagePreview() {
    const fileInput = document.getElementById('imageInput');
    const preview = document.getElementById('imagePreview');
    const file = fileInput.files[0];

    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.innerHTML = `<div class="preview-image"><img src="${e.target.result}" alt="Preview"><button type="button" class="preview-remove" onclick="removeImage()">✕</button></div>`;
        };
        reader.readAsDataURL(file);
    } else {
        preview.innerHTML = '';
    }
}

function removeImage() {
    document.getElementById('imageInput').value = '';
    document.getElementById('imagePreview').innerHTML = '';
}

function openImageModal(imageUrl) {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImage');
    modalImg.src = imageUrl;
    modal.classList.add('active');
}

function closeImageModal() {
    document.getElementById('imageModal').classList.remove('active');
}

function toggleAddContact() {
    const form = document.getElementById('addContactForm');
    const sidebar = document.querySelector('.sidebar');
    const roomsList = document.querySelector('.rooms-list');
    const sidebarFooter = document.querySelector('.sidebar-footer');
    
    form.classList.toggle('show');
    roomsList.classList.remove('show');
    sidebarFooter.classList.remove('show');
    sidebar.classList.remove('open');
    
    if (form.classList.contains('show')) {
        sidebar.classList.add('open');
        document.getElementById('searchUsername').focus();
    }
}

function toggleSidebarMenu() {
    const sidebar = document.querySelector('.sidebar');
    const form = document.getElementById('addContactForm');
    const roomsList = document.querySelector('.rooms-list');
    const sidebarFooter = document.querySelector('.sidebar-footer');
    
    sidebar.classList.toggle('open');
    
    // Close other sections
    form.classList.remove('show');
    roomsList.classList.toggle('show');
    sidebarFooter.classList.toggle('show');
}

document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('searchUsername');
    if (searchInput) {
        searchInput.addEventListener('input', async (e) => {
            const username = e.target.value.trim();
            const resultDiv = document.getElementById('searchResult');

            if (!username) {
                resultDiv.innerHTML = '';
                return;
            }

            try {
                const response = await fetch(`/api/contacts/search?username=${encodeURIComponent(username)}`);
                
                if (response.ok) {
                    const user = await response.json();
                    resultDiv.innerHTML = `
                        <div class="search-result-item">
                            <span>${user.username}</span>
                            <button onclick="addContactToList('${user.username}')">Add</button>
                        </div>
                    `;
                } else {
                    const data = await response.json();
                    resultDiv.innerHTML = `<div class="search-result-item" style="padding: 15px; text-align: center; color: #999;">${data.error}</div>`;
                }
            } catch (error) {
                console.error('Error searching user:', error);
            }
        });
    }
});

async function addContactToList(username) {
    try {
        const response = await fetch('/api/contacts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username })
        });

        const data = await response.json();

        if (response.ok) {
            alert(`Added ${username} to contacts!`);
            document.getElementById('searchUsername').value = '';
            document.getElementById('searchResult').innerHTML = '';
            toggleAddContact();
            await loadRooms();
        } else {
            alert(data.error || 'Failed to add contact');
        }
    } catch (error) {
        console.error('Error adding contact:', error);
        alert('An error occurred');
    }
}

// Initialize the chat
document.addEventListener('DOMContentLoaded', () => {
    getCurrentUser();
    
    // Poll for new messages every 2 seconds
    pollInterval = setInterval(loadMessages, 2000);

    // Scroll to bottom initially
    const container = document.getElementById('messagesContainer');
    container.scrollTop = container.scrollHeight;
});
