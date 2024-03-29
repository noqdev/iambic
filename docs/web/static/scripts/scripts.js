var elementIds = {
    gitHubOrgAnchorTag: "gitHubOrgAnchorTag"
}

function getGitOrganizationLink(org) {
    return "https://github.com/organizations/" + org + "/settings/apps"
}


function updateText(output_field, inputValue, isLink = false) {
    // return if either field is null
    if (!output_field) {
        return;
    }
    if (inputValue == null) {
        // handle the null value
        return;
    }
    var outputFields = document.querySelectorAll('#' + output_field);
    outputFields.forEach(function(output) {
        output.innerHTML = inputValue;
    });
    if (isLink) {
        updateAnchorTagHref(elementIds.gitHubOrgAnchorTag, inputValue)
    }
}

function updateAnchorTagHref(elementId, link) {
    if (!elementId || !link) {
        return
    }
    var anchorTags = document.querySelectorAll('#' + elementId);
    anchorTags.forEach(function(anchorTag) {
        anchorTag.setAttribute("href", link);
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
        return element.innerHTML;
    }
    return null;
}

function createLabel3(id, text) {
    var label = document.createElement('label');
    label.setAttribute('for', id);
    label.innerHTML = text;
    return label;
}

function escapeHtml3(html) {
    const textNode = document.createTextNode(html);
    const div = document.createElement('div');
    div.appendChild(textNode);
    return div.innerHTML;
  }


  function createLabel2(id, content) {
    return `<label id="${id}">${content}</label>`;
  }
