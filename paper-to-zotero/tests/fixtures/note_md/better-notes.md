<!-- better notes v3.3.3 test fixture -->
---
schema: 9
---
# Markdown Test Document

## Headers

# H1 Header

## H2 Header

### H3 Header

#### H4 Header

##### H5 Header

###### H6 Header

## Emphasis

*This text is italicized.* *This text is also italicized.*

**This text is bold.** **This text is also bold.**

***This text is bold and italicized.*** ***This text is also bold and italicized.***

## Links

[Link with title](https://example.com "Title") [Link without title](https://example.com)

## Images

## Blockquotes

> This is a blockquote.
> > Nested blockquote.
>
> Back to the outer blockquote.

## Lists

### Unordered List

- Item 1
  - Subitem 1.1
    - Subitem 1.1.1
- Item 2

### Ordered List

1. First item
   1. Subitem 1.1
      1. Subitem 1.1.1
2. Second item

## Code

### Inline Code

Here is some `inline code`.

### Code Block

```
def hello_world():
    print("Hello, world!")
```

## Horizontal Rules

***

This is text between horizontal rules

***

## Tables

| Header 1 | Header 2 | Header 3 |
| --- | --- | --- |
| Row 1 | Data 1.2 | Data 1.3 |
| Row 2 | Data 2.2 | Data 2.3 |

## Math

### Inline Math

This is an inline math equation: $E = mc^2$.

### Block Math

Below is a block math equation:

$$\\int_a^b f(x) \\, dx = F(b) - F(a)$$

### Complex Math

Solve the quadratic equation:

$$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$$

## Nested Elements

### Nested Code and Lists

1. Ordered list item
   - Unordered subitem
     ```
     console.log("Nested code block");
     ```
2. This is a nested math
   $$y=x^2$$
3. This is a inline math$123$ with space in list item test
4. This is a line table

   <table>
   <tbody>
   <tr>
   <td>
   <p>1</p>
   </td>
   <td>
   <p>2</p>
   </td>
   <td>
   <p>3</p>
   </td>
   </tr>
   <tr>
   <td>
   <p>4</p>
   </td>
   <td>
   <p>5</p>
   </td>
   <td>
   <p>6</p>
   </td>
   </tr>
   <tr>
   <td>
   <p>7</p>
   </td>
   <td>
   <p>8</p>
   </td>
   <td>
   <p>9</p>
   </td>
   </tr>
   </tbody>
   </table>

## Special Characters

Escape sequences for special characters: * _ \\\` [ ] ( ) # + - .

## HTML in Markdown

This is a HTML block inside Markdown.

## Highlight Text

Highlight <span style="background-color: rgba(255, 102, 102, 0.5);">text</span> is here

## Colored Text

Colored <span style="color: rgb(255, 32, 32);">text</span> is here

## Task Lists

- Completed item
- Incomplete item

## Strikethrough

<span style="text-decoration: line-through;">This text is strikethrough.</span>

## Recursive Elements

### Recursive Links and Emphasis

**[Bold link](https://example.com)**

### Recursive Emphasis

***Bold and nested italic within bold.***

## Image

IMAGE_PLACEHOLDER

## Citation

CITATION_PLACEHOLDER

## Edge Cases

### Empty Link

[Link](https://)

### Zotero Link

[Zotero Link](zotero://note/u/123456)

### Lone Asterisk

- This should not be italic.

### Broken Lists

- Item 1
  - Item 2

    Continuation of item 2 without proper indentation.

### Long Text Wrapping

This is a very long paragraph that does not have any line breaks and is intended to test how the Markdown engine handles text wrapping when there are no explicit line breaks within the text.

***

## Conclusion

This document contains a wide range of Markdown elements, including headers, lists, blockquotes, inline and block code, tables, images, links, math, and special characters. It also tests recursive and edge cases to ensure the Markdown engine is robust.
