
import unittest
import os
import tempfile
import xml.etree.ElementTree as ET
from src.remediation.xml_patcher import XmlPatcher

SAMPLE_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>1.0.0</version>
    
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>5.3.10</version>
        </dependency>
        <dependency>
            <groupId>log4j</groupId>
            <artifactId>log4j</artifactId>
            <version>1.2.17</version>
        </dependency>
    </dependencies>
    
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>"""

class TestXmlPatcher(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8')
        self.tmp.write(SAMPLE_POM)
        self.tmp.close()
        self.file_path = self.tmp.name

    def tearDown(self):
        os.remove(self.file_path)

    def test_remove_dependency(self):
        # Action: Remove log4j
        result = XmlPatcher.remove_dependency(self.file_path, "log4j")
        
        self.assertTrue(result.success)
        self.assertIn("Successfully removed", result.message)
        
        # Verify Content
        tree = ET.parse(self.file_path)
        root = tree.getroot()
        
        # Check if log4j is gone
        # Note: simplistic check for demo
        content = open(self.file_path).read()
        # Verify spring-core is present (namespace agnostic check logic or just loosen assert)
        # Simply checking for artifactId spring-core is usually enough if we ignore namespace prefix in grep
        self.assertIn("spring-core", content) 
        self.assertNotIn("log4j", content)

    def test_remove_plugin(self):
        # Action: Remove maven-compiler-plugin
        result = XmlPatcher.remove_plugin(self.file_path, "maven-compiler-plugin")
        
        self.assertTrue(result.success)
        
        content = open(self.file_path).read()
        self.assertNotIn("<artifactId>maven-compiler-plugin</artifactId>", content)

    def test_not_found(self):
        result = XmlPatcher.remove_dependency(self.file_path, "missing-lib")
        self.assertFalse(result.success)
        self.assertIn("Could not find", result.message)

    def test_validation(self):
        # Valid case
        valid, msg = XmlPatcher.validate_xml(self.file_path)
        # We accept either True (xmllint) or True (fallback)
        self.assertTrue(valid, f"Validation failed: {msg}")
        
        # Broken case
        with open(self.file_path, 'w') as f:
            f.write("<project>Broken")
            
        valid, msg = XmlPatcher.validate_xml(self.file_path)
        self.assertFalse(valid)

if __name__ == "__main__":
    unittest.main()
