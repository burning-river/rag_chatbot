document.addEventListener('DOMContentLoaded', function() {
    const pdfForm = document.getElementById('pdf-form');
    const chatForm = document.getElementById('chat-form');
    const chatHistory = document.getElementById('chat-history');
    const userInput = document.getElementById('user-input');
    const uploadStatus = document.getElementById('upload-status');
    const followupSection = document.getElementById('followup-section');
    const followupText = document.getElementById('followup-text');
    const followupBtn = document.getElementById('followup-btn');
    
    let currentFollowup = null;
    
    // Handle PDF upload
    pdfForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const fileInput = document.getElementById('pdf-file');
        const file = fileInput.files[0];
        
        if (!file) {
            alert('Please select a PDF file');
            return;
        }
        
        const formData = new FormData();
        formData.append('file', file);
        
        uploadStatus.textContent = 'Uploading and processing PDF...';
        uploadStatus.classList.remove('d-none', 'alert-danger');
        uploadStatus.classList.add('alert-info');
        
        try {
            const response = await fetch('/upload-pdf/', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (response.ok) {
                uploadStatus.textContent = `PDF "${result.filename}" processed successfully. You can now ask questions!`;
                uploadStatus.classList.remove('alert-info');
                uploadStatus.classList.add('alert-success');
                
                // Add system message to chat
                addBotMessage("PDF loaded successfully. What would you like to know about this document?");
            } else {
                uploadStatus.textContent = 'Error processing PDF: ' + (result.detail || 'Unknown error');
                uploadStatus.classList.remove('alert-info');
                uploadStatus.classList.add('alert-danger');
            }
        } catch (error) {
            uploadStatus.textContent = 'Error: ' + error.message;
            uploadStatus.classList.remove('alert-info');
            uploadStatus.classList.add('alert-danger');
        }
    });
    
    // Handle chat form submission
    chatForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const question = userInput.value.trim();
        if (!question) return;
        
        // Add user message to chat
        addUserMessage(question);
        
        // Clear input and hide followup
        userInput.value = '';
        followupSection.classList.add('d-none');
        
        // Show typing indicator
        showTypingIndicator();
        
        try {
            const response = await fetch('/chat/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    question: question,
                    use_followup: false
                })
            });
            
            const result = await response.json();
            
            // Remove typing indicator
            removeTypingIndicator();
            
            // Add bot response
            addBotMessage(result.answer);
            
            // Show followup if available
            if (result.followup) {
                followupText.textContent = result.followup;
                followupSection.classList.remove('d-none');
                currentFollowup = result.followup;
            }
        } catch (error) {
            removeTypingIndicator();
            addBotMessage('Error: ' + error.message);
        }
    });
    
    // Handle followup button click
    followupBtn.addEventListener('click', async function() {
        if (!currentFollowup) return;
        
        // Add user message to chat
        addUserMessage(currentFollowup);
        
        // Hide followup section
        followupSection.classList.add('d-none');
        
        // Show typing indicator
        showTypingIndicator();
        
        try {
            const response = await fetch('/chat/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    question: "",
                    use_followup: true,
                    followup_text: currentFollowup
                })
            });
            
            const result = await response.json();
            
            // Remove typing indicator
            removeTypingIndicator();
            
            // Add bot response
            addBotMessage(result.answer);
            
            // Show new followup if available
            if (result.followup) {
                followupText.textContent = result.followup;
                followupSection.classList.remove('d-none');
                currentFollowup = result.followup;
            } else {
                currentFollowup = null;
            }
        } catch (error) {
            removeTypingIndicator();
            addBotMessage('Error: ' + error.message);
        }
    });
    
    // Helper functions
    function addUserMessage(text) {
        const messageContainer = document.createElement('div');
        messageContainer.className = 'message-container';
        
        const message = document.createElement('div');
        message.className = 'message user-message';
        message.textContent = text;
        
        messageContainer.appendChild(message);
        chatHistory.appendChild(messageContainer);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
    
    function addBotMessage(text) {
        const messageContainer = document.createElement('div');
        messageContainer.className = 'message-container';
        
        const message = document.createElement('div');
        message.className = 'message bot-message';
        message.textContent = text;
        
        messageContainer.appendChild(message);
        chatHistory.appendChild(messageContainer);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
    
    function showTypingIndicator() {
        const indicatorContainer = document.createElement('div');
        indicatorContainer.className = 'message-container';
        indicatorContainer.id = 'typing-indicator-container';
        
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.innerHTML = '<span></span><span></span><span></span>';
        
        indicatorContainer.appendChild(indicator);
        chatHistory.appendChild(indicatorContainer);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
    
    function removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator-container');
        if (indicator) {
            indicator.remove();
        }
    }
});
