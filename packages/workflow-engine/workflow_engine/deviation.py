"""Deviation Detection Engine - Compare actual workflow vs DMS/system workflow."""
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from enum import Enum
import pandas as pd


class DeviationType(str, Enum):
    MISSING_CAPTURE = "MISSING_CAPTURE"
    MISSING_DMS_STEP = "MISSING_DMS_STEP"
    TIMESTAMP_MISMATCH = "TIMESTAMP_MISMATCH"
    WRONG_SEQUENCE = "WRONG_SEQUENCE"
    SKIPPED_HANDOFF = "SKIPPED_HANDOFF"
    MANPOWER_MISMATCH = "MANPOWER_MISMATCH"
    DELAYED_PROCESSING = "DELAYED_PROCESSING"
    IDLE_TOO_LONG = "IDLE_TOO_LONG"
    BILLING_BEFORE_EVIDENCE = "BILLING_BEFORE_EVIDENCE"


@dataclass
class Deviation:
    deviation_type: DeviationType
    job_card_id: str
    stage_code: str
    description: str
    expected_time: Optional[datetime]
    actual_time: Optional[datetime]
    severity: str  # LOW, MEDIUM, HIGH
    details: Dict


class DeviationEngine:
    """
    Detects deviations between actual captured workflow and DMS/system workflow.
    """
    
    STAGE_SEQUENCE = [
        "GATE_ENTRY", "ADVISOR_RECEIPT", "TECH_ACCEPT", "DIAGNOSIS",
        "PARTS_WAIT", "PARTS_ISSUED", "WASHING", "QC_START", "QC_DONE",
        "READY_DELIVERY", "EXIT"
    ]
    
    MAX_STAGE_DURATION = {
        "WASHING": timedelta(minutes=30),
        "QC_START": timedelta(minutes=60),
        "TECH_ACCEPT": timedelta(hours=2),
    }
    
    async def detect_deviations(self, job_card_id: str) -> List[Deviation]:
        """Detect all deviations for a job card."""
        deviations = []
        
        # Get actual events
        actual_events = await self._get_capture_events(job_card_id)
        
        # Get expected events from DMS
        expected_events = await self._get_dms_timeline(job_card_id)
        
        # Check for missing captures
        deviations.extend(self._check_missing_captures(expected_events, actual_events))
        
        # Check for sequence errors
        deviations.extend(self._check_sequence(actual_events))
        
        # Check for delays
        deviations.extend(self._check_delays(actual_events))
        
        return deviations
    
    def _check_missing_captures(
        self, 
        expected: List[Dict], 
        actual: List[Dict]
    ) -> List[Deviation]:
        """Check for stages that should have evidence but don't."""
        deviations = []
        
        expected_stages = {e.get("stage_code") for e in expected if e.get("requires_capture")}
        actual_stages = {e.get("stage_code") for e in actual}
        
        for stage in expected_stages:
            if stage not in actual_stages:
                deviations.append(Deviation(
                    deviation_type=DeviationType.MISSING_CAPTURE,
                    job_card_id="jc_001",
                    stage_code=stage,
                    description=f"No capture evidence for stage: {stage}",
                    expected_time=None,
                    actual_time=None,
                    severity="HIGH",
                    details={"expected_stage": stage}
                ))
        
        return deviations
    
    def _check_sequence(self, events: List[Dict]) -> List[Deviation]:
        """Check for wrong sequence in events."""
        deviations = []
        event_stages = [e.get("stage_code") for e in events]
        
        # Check if stages are out of order
        for i in range(1, len(event_stages)):
            prev_stage = event_stages[i-1]
            curr_stage = event_stages[i]
            
            if prev_stage in self.STAGE_SEQUENCE and curr_stage in self.STAGE_SEQUENCE:
                prev_idx = self.STAGE_SEQUENCE.index(prev_stage)
                curr_idx = self.STAGE_SEQUENCE.index(curr_stage)
                
                if curr_idx < prev_idx:
                    deviations.append(Deviation(
                        deviation_type=DeviationType.WRONG_SEQUENCE,
                        job_card_id="jc_001",
                        stage_code=curr_stage,
                        description=f"Stage {curr_stage} occurred after {prev_stage}",
                        expected_time=None,
                        actual_time=events[i].get("captured_at"),
                        severity="MEDIUM",
                        details={"previous_stage": prev_stage}
                    ))
        
        return deviations
    
    def _check_delays(self, events: List[Dict]) -> List[Deviation]:
        """Check for excessive idle time between stages."""
        deviations = []
        
        for i in range(1, len(events)):
            prev_time = events[i-1].get("captured_at")
            curr_time = events[i].get("captured_at")
            
            if prev_time and curr_time:
                duration = curr_time - prev_time
                stage = events[i].get("stage_code")
                
                if stage in self.MAX_STAGE_DURATION:
                    max_duration = self.MAX_STAGE_DURATION[stage]
                    if duration > max_duration:
                        deviations.append(Deviation(
                            deviation_type=DeviationType.IDLE_TOO_LONG,
                            job_card_id="jc_001",
                            stage_code=stage,
                            description=f"Stage {stage} took {duration} (max: {max_duration})",
                            expected_time=prev_time + max_duration,
                            actual_time=curr_time,
                            severity="MEDIUM",
                            details={"actual_duration": str(duration)}
                        ))
        
        return deviations
    
    async def _get_capture_events(self, job_card_id: str) -> List[Dict]:
        """Fetch actual capture events from database."""
        # Placeholder - will integrate with DB
        return []
    
    async def _get_dms_timeline(self, job_card_id: str) -> List[Dict]:
        """Fetch expected timeline from DMS."""
        # Placeholder - will integrate with DMS adapter
        return []