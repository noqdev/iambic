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