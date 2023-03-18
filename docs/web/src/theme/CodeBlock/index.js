// src/theme/CodeBlock/index.js
import React from 'react';
import OriginalCodeBlock from '@theme-original/CodeBlock';

const CodeBlock = (props) => {
  const { children } = props;
  const codeWithLabel = children.replace(/&lt;label(.*?)&gt;/g, '<label$1>').replace(/&lt;\/label&gt;/g, '</label>');

  return <OriginalCodeBlock {...props} children={codeWithLabel} />;
};

export default CodeBlock;
