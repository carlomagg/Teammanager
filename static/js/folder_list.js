document.addEventListener('DOMContentLoaded', () => {
    window.ajaxRenameFolder = function(folderId) {
        const input = document.querySelector(`#renameFolderModal${folderId} input[name="name"]`);
        if (!input) return console.error('Input not found');
        fetch(`documents/folders/${folderId}/rename/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('input[name="csrfmiddlewaretoken"]').value,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `name=${encodeURIComponent(input.value)}`
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                document.querySelector(`#renameFolderModal${folderId}`).classList.remove('show');
                location.reload();
            }
        })
        .catch(err => console.error('Error renaming folder:', err));
    };

    window.ajaxMoveFolder = function(folderId) {
        const select = document.querySelector(`#moveFolderModal${folderId} select[name="new_parent_id"]`);
        if (!select) return console.error('Select not found');
        fetch(`documents/folders/${folderId}/move/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('input[name="csrfmiddlewaretoken"]').value,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `new_parent_id=${encodeURIComponent(select.value)}`
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                document.querySelector(`#moveFolderModal${folderId}`).classList.remove('show');
                location.reload();
            }
        })
        .catch(err => console.error('Error moving folder:', err));
    };

    window.ajaxRenameFile = function(fileId) {
        const input = document.querySelector(`#renameFileModal${fileId} input[name="name"]`);
        if (!input) return console.error('Input not found');
        fetch(`documents/folders/files/${fileId}/rename/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('input[name="csrfmiddlewaretoken"]').value,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `name=${encodeURIComponent(input.value)}`
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                document.querySelector(`#renameFileModal${fileId}`).classList.remove('show');
                location.reload();
            }
        })
        .catch(err => console.error('Error renaming file:', err));
    };

    window.ajaxMoveFile = function(fileId) {
        const select = document.querySelector(`#moveFileModal${fileId} select[name="new_folder_id"]`);
        if (!select) return console.error('Select not found');
        fetch(`documents/folders/files/${fileId}/move/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': document.querySelector('input[name="csrfmiddlewaretoken"]').value,
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `new_folder_id=${encodeURIComponent(select.value)}`
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                document.querySelector(`#moveFileModal${fileId}`).classList.remove('show');
                location.reload();
            }
        })
        .catch(err => console.error('Error moving file:', err));
    };

    new Sortable(document.querySelector('#sortable-row'), {
        animation: 150,
        onEnd: function (evt) {
            const folderId = evt.item.dataset.folderId;
            if (folderId) {
                const newParentId = prompt("Enter new parent folder ID:");
                if (newParentId) {
                    fetch(`documents/folders/${folderId}/move/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': document.querySelector('input[name="csrfmiddlewaretoken"]').value,
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: `new_parent_id=${encodeURIComponent(newParentId)}`
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            location.reload();
                        }
                    })
                    .catch(err => console.error('Error moving folder:', err));
                }
            }
        }
    });

    document.querySelectorAll('[data-bs-toggle="dropdown"]').forEach(button => {
        button.addEventListener('click', () => {
            console.log('Dropdown button clicked');
        });
    });
});