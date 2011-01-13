import codecs
import logging
import os
import os.path
import re
import subprocess
import time

class History:
    """
    Represents the complete history of a single Git repository. Initialize
    with a file path pointing to a valid Git repo; does not currently
    support git: or http: URLs.
    """
    
    def __init__(self, path, log=logging.NOTSET):
        self.log = log
        if self.log:
            self.logger = logging.getLogger('pygitlog.History')
        else:
            self.logger = NullLogger()
        
        # Normalize and store path
        if path[0] == '~':
            path = os.path.expanduser(path)
        self.path = os.path.normpath(path)
        
        self.logger.info("Created GitHistory with path " + self.path)
        
        # Grab and store commit info
        #os.chdir(self.path)
        #logText = subprocess.getoutput("git log --pretty=raw")
        logLines = []
        logProcess = subprocess.Popen("git log --pretty=raw", stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.path, shell=True)
        for line in logProcess.stdout:
            logLines.append(str(bytes([b for b in line if b < 128]), 'ascii', 'replace'))
        logText = "".join(logLines)
        
        # Parse commit info
        stime = time.time()
        p = Parser(log=self.log)
        p.parse(logText)
        self.commits = p.getCommits()
        self.authors = p.getAuthors()
        etime = time.time()
        
        self.logger.info("Parsing complete:")
        self.logger.info("    {} commits".format(len(self.commits)))
        self.logger.info("    {} authors".format(len(self.authors)))
        self.logger.info("    {} committers".format(len(self.authors)))
        self.logger.info("    Operation took {} seconds".format(etime - stime))
    
    def authorWithName(self, name):
        for aKey in self.authors:
            if self.authors[aKey].name == name:
                return self.authors[aKey]

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
    
    def clear(self):
        """
        Remove any past results from this parser.
        """
        self._currentCommit = None
        self._commits = {}
        self._authors = {}
        self._committers = {}
        self._developers = {}
    
    def parse(self, text):
        """
        Parse the raw text of a Git history into a list of GitCommit
        objects. Expects a single unbroken string (not a list of
        strings representing lines). Clears any past parse results
        stored in this Parser.
        """
        
        self.clear()
        lines = text.split("\n")
        self.logger.info("Parsing Git history")
        
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
                self.logger.debug("Found key-value pair: {0} {1}".format(keyword, content))
                
                self._handleKeyValue(keyword, content)
        
        # Grab the last commit
        self._commits[self._currentCommit.hashKey] = self._currentCommit
        self._currentCommit = None
        
        # Finalize the commit tree
        self._resolveCommits()
    
    def getCommits(self):
        return self._commits
    
    def getAuthors(self):
        return self._authors
    
    def _handleKeyValue(self, keyword, content):
        if keyword == "commit":
            if not self._currentCommit == None:
                self._commits[self._currentCommit.hashKey] = self._currentCommit
            self._currentCommit = Commit(hashKey=content)
            
        elif keyword == "author":
            (developer, timestamp) = self._findDeveloperAndTimestamp(content)
            
            if not str(developer) in self._authors:
                self._authors[str(developer)] = developer
            self._currentCommit.author = developer
            self._authors[str(developer)].commits[self._currentCommit.hashKey] = self._currentCommit
            
        elif keyword == "committer":
            (developer, timestamp) = self._findDeveloperAndTimestamp(content)
            
            if not str(developer) in self._committers:
                self._committers[str(developer)] = developer
            self._currentCommit.committer = developer
            
        elif keyword == "parent":
            if content in self._commits:
                self._currentCommit.parents[content] = self._commits[content]
            else:
                self._currentCommit.parents[content] = content
            
        elif keyword == "tree":
            self._currentCommit.tree = content
            
        else:
            self.logger.warn("Ignoring unrecognized commit keyword: " + keyword)
    
    def _findDeveloperAndTimestamp(self, text):
        """
        Given a line of text, break out a Developer and Timestamp object.
        Returns a tuple (dev, ts).
        """
        
        parts = text.split(' ')
        
        tz = parts.pop()
        epoch = parts.pop()
        timestamp = Timestamp(epoch, tz)
        
        # Get Developer, either from cache or by making new object
        devKey = ' '.join(parts)
        if devKey in self._developers:
            developer = self._developers[devKey]
        else:
            email = (re.findall("<.*>", devKey))[0].replace("<", "").replace(">", "")
            self.logger.debug("Found author email {0}".format(email))
            name = devKey.replace(" <{0}>".format(email), "")
            self.logger.debug("Found author name {0}".format(name))
            developer = Developer(name=name, email=email)
            self._developers[devKey] = developer
        
        return (developer, timestamp)
    
    def _resolveCommits(self):
        """
        Iterate through all Commits being processed and replace any parent
        hash key placeholders with their corresponding Commit objects.
        Typically run at the end of a parse to ensure that all Commits are
        linked properly.
        """
        
        self.logger.info("Resolving {0} commit parents".format(sum(map((lambda x : len([p for p in self._commits[x].parents if isinstance(self._commits[x].parents[p], str)])), self._commits))))
        for hashKey in self._commits:
            for parentKey in self._commits[hashKey].parents:
                if isinstance(self._commits[hashKey].parents[parentKey], str):
                    self.logger.debug("Replacing parent key {0} with actual commit".format(parentKey))
                    self._commits[hashKey].parents[parentKey] = self._commits[parentKey]

class Commit:
    """
    Represents a single commit to a Git repository. A commit is identified
    by its hash, author, parents, and tree, where:
     - hash is the string SHA1 hash of the commit blob
     - author is a Developer who wrote the change
     - committer is a Developer who committed the change
     - parents is a list of Commit objects that are this Commit's parents
     - tree is the string SHA1 hash of the commit blob's tree blob
    """
    
    def __init__(self, hashKey, author=None, committer=None, parents=None, tree=None):
        self.hashKey = hashKey
        self.author = author
        self.committer = committer
        if not isinstance(parents, dict):
            self.parents = {}
        else:
            self.parents = parents
        self.tree = tree

class Developer:
    def __init__(self, name, email):
        self.name = name
        self.email = email
        self.commits = {}
    
    def __str__(self):
        return "{0} <{1}>".format(self.name, self.email)

class Timestamp:
    def __init__(self, epoch, timezone):
        self.epoch = epoch
        self.timezone = timezone

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
logging.basicConfig(filename="pygitlog.log", level=logging.INFO, filemode='w')