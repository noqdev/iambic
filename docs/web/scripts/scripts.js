function updateText(input_field, output_field) {
    // return if either field is null
    if (!input_field || !output_field) {
        return;
    }
    var inputValue = input_field.value;
    if (inputValue == null) {
        // handle the null value
        return;
    }
    var outputFields = document.querySelectorAll('#' + output_field);
    outputFields.forEach(function(output) {
        output.innerHTML = inputValue;
    });
}

function updateFieldValue(field, value) {
    var fields = document.querySelectorAll('#' + field);
    fields.forEach(function(f) {
        f.value = value;
    });
}

function replaceString(str, input_field, default_value) {
    var inputValue = input_field.value;
    if (inputValue == null) {
        inputValue = default_value;
    }
    var html = document.documentElement.innerHTML;
    html = html.replace(new RegExp(str, 'g'), inputValue);
    document.documentElement.innerHTML = html;
}

function getElementValue(id) {
    var element = document.getElementById(id);
    if (element) {
        return element.value;
    }
    return null;
}


