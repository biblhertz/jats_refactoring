# Scripts to prepare JATS files for inDesign XML import
With the provided `biblio2.py` script and the `htmlbiblio2xml.xslt` stylesheet, you have a comprehensive workflow for converting a BibTeX bibliography to an XML format suitable for InDesign, following an intermediate HTML conversion step (for the bibliography). To coordinate this with your JATS article processing (`article2indesign.py`) and the eventual merging of the article and bibliography into a final document.
With the `combine.py` script, you now have a complete workflow for processing a JATS article, converting a bibliography into XML, and combining both into a single XML document ready for InDesign. This script effectively merges the article and bibliography XML files by appending the bibliography to the `<back>` section of the article XML.

### Automated Workflow

1. **Process the JATS Article**: First, use `article2indesign.py` to transform the JATS XML with the provided XSLT and create an InDesign-ready XML document.

2. **Convert the Bibliography**: Next, run `biblio2.py` to convert the bibliography from BibTeX to XML, applying the necessary transformations.

3. **Merge Article and Bibliography**: Finally, use `combine.py` to merge the XML outputs from the first two steps into a single XML document.


## Single steps:

### Step 1: Process JATS Article
First, use `article2indesign.py` to process the JATS article (`jatsarticle.xml`) with the `jats2idml.xslt`. This script applies an XSLT transformation to the JATS XML and outputs a minified and transformed XML file ready for InDesign. The existing references are ignored.

``` bash
python article2indesign.py jatsarticle.xml jats2idml.xslt
```

### Step 2: Convert Bibliography
Next, run `biblio2.py` to convert the article BibTeX file (`bibliogrpahy.bib`) into an XML format via an intermediate HTML representation (`biblio_output.html`). This involves:
- Converting the BibTeX file to HTML using Pandoc with a specified CSL style `yourcsl.csl`.
- Applying an XSLT transformation `htmlbiblio2xml.xslt` to the HTML to produce the final XML bibliography.
``` bash
python biblio2.py -i bibliography.bib -o biblio_output.html -c yourcsl.csl -x htmlbiblio2xml.xslt
```

### Step 3: Merge Article and Bibliography
Finally, `combine.py` script helps to merge the XML outputs from Steps 1 and 2. This script will:
- Load the XML file generated by `article2indesign.py`.
- Load the XML bibliography file generated by `biblio2.py`.
- Combine these XML documents into a single XML file that integrates the article content with the bibliography in the desired structure for InDesign.

## Prerequisites

### External Tools
- **Pandoc**: A universal document converter, used in `biblio2.py` for converting BibTeX files to HTML.
  - Installation instructions can be found on the [Pandoc installation page](https://pandoc.org/installing.html).
- **Python**: Ensure you have Python installed to run the scripts, and pip updated to install needed libraries.
  - Python can be downloaded from [python.org](https://www.python.org/downloads/).

### Python Libraries
- **lxml**: For parsing, creating, and saving XML documents. Used in all your Python scripts for handling XML and XSLT transformations.
  - Installation command: `pip install lxml`
- **argparse**: For parsing command-line arguments in your scripts. This is a standard library module in Python, so no additional installation should be required for Python versions 2.7 and 3.2 and above.
- **subprocess**: For running external commands (e.g., calling other scripts or running Pandoc). This is also part of Python's standard library, so no additional installation is required.
 - **xmlformatter** for minifying and formatting XML content.

### Installation Summary

```bash
# clone the repository
# Install lxml
pip install lxml
# Install xmlformatter
pip install xmlformatter

# Install Pandoc (follow the specific instructions for your OS)
```

Ensure that Python is installed and that you can run `python` or `python3` from your command line or terminal. Also, verify that Pandoc is correctly installed by running `pandoc --version`.