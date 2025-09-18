"""Test for the markdown cleaner module."""

import unittest
from pathlib import Path
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.forma.shared.utils.markdown_cleaner import MarkdownCleaner


class TestMarkdownCleaner(unittest.TestCase):
    """Test cases for the MarkdownCleaner class."""

    def test_clean_markdown_empty_content(self):
        """Test cleaning empty content."""
        content = ""
        cleaned = MarkdownCleaner.clean_markdown(content)
        self.assertEqual(cleaned, "")

    def test_clean_markdown_excessive_newlines(self):
        """Test cleaning content with excessive newlines."""
        content = "# Title\n\n\n\n\nThis is a paragraph.\n\n\n\nAnother paragraph."
        cleaned = MarkdownCleaner.clean_markdown(content)
        self.assertEqual(cleaned, "# Title\n\nThis is a paragraph.\n\nAnother paragraph.")

    def test_clean_markdown_empty_sections(self):
        """Test cleaning content with empty sections between horizontal rules."""
        content = "# Title\n\n---\n\n\n\n---\n\nContent after."
        cleaned = MarkdownCleaner.clean_markdown(content)
        self.assertEqual(cleaned, "# Title\n\n---\n\nContent after.")

    def test_clean_markdown_multiple_horizontal_rules(self):
        """Test cleaning content with multiple consecutive horizontal rules."""
        content = "# Title\n\n---\n\n---\n\n---\n\n---\n\n---\n\n---\n\nContent after."
        cleaned = MarkdownCleaner.clean_markdown(content)
        self.assertEqual(cleaned, "# Title\n\n---\n\nContent after.")

    def test_clean_markdown_real_world_example(self):
        """Test cleaning a real-world example with multiple issues."""
        content = """# Document Title



## Section 1


This is some content.



---



---



---


## Section 2

This is more content.




Another paragraph."""
        
        expected = """# Document Title

## Section 1

This is some content.

---

## Section 2

This is more content.

Another paragraph."""
        
        cleaned = MarkdownCleaner.clean_markdown(content)
        self.assertEqual(cleaned, expected)


    def test_clean_markdown_trailing_image_descriptions(self):
        """Test cleaning content with trailing image descriptions."""
        content = """# Document Title

This is some content.

> **Image Desc 1**: A simple image
> **Image Desc 2**: Another image
> **Image Desc 3**: Yet another image
"""
        
        expected = """# Document Title

This is some content.
"""
        
        cleaned = MarkdownCleaner.clean_markdown(content)
        self.assertEqual(cleaned, expected)
    
    def test_clean_markdown_complex_separators(self):
        """Test cleaning content with complex separator patterns."""
        content = """# Document Title

This is some content.

--- 

---  

---

More content.
"""
        
        expected = """# Document Title

This is some content.

---

More content.
"""
        
        cleaned = MarkdownCleaner.clean_markdown(content)
        self.assertEqual(cleaned, expected)

    def test_clean_markdown_large_content(self):
        """Test cleaning a large content that would potentially cause backtracking issues."""
        # Create a large content with many separators and image descriptions
        separators = "---\n" * 100
        image_descs = "\n".join([f"> **Image Desc {i}**: Description {i}" for i in range(1, 101)])
        content = f"# Document Title\n\nThis is some content.\n\n{separators}\n\nMore content.\n\n{image_descs}"
        
        # The expected result should have only one separator and no trailing image descriptions
        expected = "# Document Title\n\nThis is some content.\n\n---\n\nMore content.\n"
        
        cleaned = MarkdownCleaner.clean_markdown(content)
        self.assertEqual(cleaned, expected)

if __name__ == "__main__":
    unittest.main()
