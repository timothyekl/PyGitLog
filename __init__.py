import logging
import os
import os.path
import subprocess
import time

class History:
    """
    Represents the complete history of a single Git repository. Initialize
    with a file path pointing to a valid Git repo; does not currently
    support git: or http: URLs.
    """
    
    def __init__(self, path, log=False):
        self.log = log
        if self.log:
            self.logger = logging.getLogger('pygitlog.History')
        else:
            self.logger = NullLogger()
        
        # Normalize and store path
        if path[0] == '~':
            path = os.path.expanduser(path)
        self.path = os.path.normpath(path)
        
        self.logger.info("Created GitHistory from path " + self.path)
        
        # Grab and store commit info
        os.chdir(self.path)
        logText = subprocess.getoutput("git log --pretty=raw")
        
        # Parse commit info
        stime = time.time()
        p = Parser(log=self.log)
        self.commits = p.parse(logText)
        etime = time.time()
        self.logger.info("Found {0} commits in {1} seconds".format(len(self.commits), etime - stime))
    

class Parser:
    """
    Provides a single class for all log-parsing needs.
    """
    
    def __init__(self, log=False):
        self.log = log
        if self.log:
            self.logger = logging.getLogger('pygitlog.Parser')
        else:
            self.logger = NullLogger()
    
    def parse(self, text):
        """
        Parse the raw text of a Git history into a list of GitCommit
        objects. Expects a single unbroken string (not a list of
        strings representing lines).
        """
        
        lines = text.split("\n")
        
        self._currentCommit = None
        self._commits = []
        
        for line in lines:
            if len(line) == 0:
                # Line is a spacer
                pass
                
            elif line[0] == ' ':
                # Line is part of a commit message
                pass
                
            else:
                # Line is part of a commit header
                spaceIdx = line.find(' ')
                if spaceIdx == -1:
                    self.logger.warn("Skipping unrecognizable history line: " + line)
                    continue
                
                keyword = line[:spaceIdx]
                content = line[spaceIdx+1:]
                self.logger.info("Found key-value pair: {0} {1}".format(keyword, content))
                
                self._handleKeyValue(keyword, content)
        
        # Grab the last commit and be done
        self._commits.append(self._currentCommit)
        self._currentCommit = None
        return self._commits
    
    def _handleKeyValue(self, keyword, content):
        if keyword == "commit":
            if not self._currentCommit == None:
                self._commits.append(self._currentCommit)
            self._currentCommit = Commit()
        else:
            self.logger.warn("Ignoring unrecognized commit keyword: " + keyword)

class Commit:
    def __init__(self):
        pass

class NullLogger:
    """
    Convenience class that ignores all log messages sent to it.
    """
    
    def debug(self, text):
        pass
    def info(self, text):
        pass
    def warn(self, text):
        pass
    def error(self, text):
        pass
    def critical(self, text):
        pass

# Set up logging
logging.basicConfig(filename="pygitlog.log", level=logging.DEBUG, filemode='w')