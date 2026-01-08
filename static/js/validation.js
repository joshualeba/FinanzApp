document.addEventListener('DOMContentLoaded', function() {
    // Select all forms that need validation
    const forms = document.querySelectorAll('form.needs-validation');

    forms.forEach(form => {
        const inputs = form.querySelectorAll('input');
        const submitBtn = form.querySelector('button[type="submit"]');

        inputs.forEach(input => {
            // Create status icon wrapper
            const wrapper = document.createElement('div');
            wrapper.className = 'input-wrapper';
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);

            const icon = document.createElement('span');
            icon.className = 'validation-icon';
            wrapper.appendChild(icon);

            input.addEventListener('input', () => validateInput(input, icon));
            input.addEventListener('blur', () => validateInput(input, icon));
        });

        // Initial check
        form.addEventListener('input', () => {
            const allValid = Array.from(inputs).every(input => checkValidity(input));
            submitBtn.disabled = !allValid;
            submitBtn.style.opacity = allValid ? '1' : '0.5';
            submitBtn.style.cursor = allValid ? 'pointer' : 'not-allowed';
        });
    });

    function validateInput(input, icon) {
        if (input.value.length === 0) {
            setInputStatus(input, icon, 'neutral');
            return;
        }

        const isValid = checkValidity(input);
        setInputStatus(input, icon, isValid ? 'valid' : 'invalid');
    }

    function checkValidity(input) {
        const type = input.type;
        const name = input.name;
        const value = input.value;

        if (name === 'username') {
            // 1 uppercase, no weird chars, min 3
            return /^[A-Z][a-zA-Z0-9_]{2,}$/.test(value);
        }

        if (type === 'email') {
            return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
        }

        if (name === 'password') {
            // 8-25 chars, 1 uppercase, 1 special char
            const length = value.length >= 8 && value.length <= 25;
            const uppercase = /[A-Z]/.test(value);
            const special = /[!@#$%^&*(),.?":{}|<>]/.test(value);
            return length && uppercase && special;
        }

        return input.checkValidity();
    }

    function setInputStatus(input, icon, status) {
        input.classList.remove('is-valid', 'is-invalid');
        icon.innerHTML = '';
        
        if (status === 'valid') {
            input.classList.add('is-valid');
            icon.innerHTML = '✓';
            icon.style.color = '#10b981'; // Green
        } else if (status === 'invalid') {
            input.classList.add('is-invalid');
            icon.innerHTML = '✕';
            icon.style.color = '#ef4444'; // Red
        }
    }
});
