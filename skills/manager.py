"""Skill manager for loading and managing agent skills."""

from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass
from utils.logger import logger


@dataclass
class Skill:
    """Represents a single skill."""
    name: str
    description: str
    prompt: str
    path: Path


class SkillManager:
    """Manages skills loading and activation."""
    
    def __init__(self, skills_path: Path):
        """Initialize skill manager.
        
        Args:
            skills_path: Path to skills directory
        """
        self.skills_path = Path(skills_path)
        self.skills: Dict[str, Skill] = {}
        self._load_skills()
    
    def _load_skills(self):
        """Load all available skills from the skills directory."""
        if not self.skills_path.exists():
            logger.warning(f"Skills directory not found: {self.skills_path}")
            return
        
        try:
            # Look for skill.py files in subdirectories
            for skill_dir in self.skills_path.iterdir():
                if not skill_dir.is_dir():
                    continue
                
                # Look for SKILL.md or skill.json config
                skill_config = skill_dir / "SKILL.md"
                if skill_config.exists():
                    self._load_skill_from_file(skill_dir, skill_config)
            
            logger.info(f"Loaded {len(self.skills)} skills from {self.skills_path}")
        except Exception as e:
            logger.warning(f"Error loading skills: {e}")
    
    def _load_skill_from_file(self, skill_dir: Path, config_file: Path):
        """Load a single skill from config file."""
        try:
            # Parse skill metadata from config
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract name from directory
            name = skill_dir.name
            
            # Extract description from first line of config
            description = content.split('\n')[0].replace('#', '').strip()
            
            # For now, use config content as prompt
            prompt = content[:500] if len(content) > 500 else content
            
            skill = Skill(
                name=name,
                description=description,
                prompt=prompt,
                path=skill_dir
            )
            
            self.skills[name] = skill
            logger.debug(f"Loaded skill: {name}")
            
        except Exception as e:
            logger.warning(f"Error loading skill from {config_file}: {e}")
    
    def get_skill(self, skill_name: str) -> Optional[Skill]:
        """Get a skill by name.
        
        Args:
            skill_name: Name of the skill
            
        Returns:
            Skill object or None if not found
        """
        return self.skills.get(skill_name)
    
    def list_skills(self) -> List[str]:
        """List all available skills.
        
        Returns:
            List of skill names
        """
        return list(self.skills.keys())
    
    def get_skill_info(self, skill_name: str) -> Dict:
        """Get information about a skill.
        
        Args:
            skill_name: Name of the skill
            
        Returns:
            Dict with skill information
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return {}
        
        return {
            'name': skill.name,
            'description': skill.description,
            'path': str(skill.path)
        }
