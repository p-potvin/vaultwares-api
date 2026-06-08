"""
Base workflow infrastructure.

A :class:`Workflow` is an ordered sequence of :class:`Step` objects that
transforms an arbitrary input through a pipeline.  It is deliberately
simple – each step is just a callable – so that existing functions from
any module can be wired together without subclassing.

Usage::

    from ai_model.workflows.base import Workflow, Step

    wf = Workflow(name="MyPipeline")
    wf.add_step(Step("load",    lambda ctx: ctx.update(image=load_image(ctx["path"])) or ctx))
    wf.add_step(Step("sharpen", lambda ctx: ctx.update(image=sharpen(ctx["image"])) or ctx))
    wf.add_step(Step("caption", lambda ctx: ctx.update(caption=model.caption(ctx["image"])) or ctx))

    result = wf.run({"path": "photo.jpg"})
    print(result["caption"])
"""

from __future__ import annotations

import logging
import random
import string
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ai_model.adk_imports import AgentStatus, ExtrovertAgent

logger = logging.getLogger(__name__)


@dataclass
class Step:
    """A single pipeline step.

    Attributes
    ----------
    name:
        Human-readable name shown in logs.
    fn:
        Callable that accepts the pipeline context dict and returns an
        updated context dict.  Must not mutate the input in place (use
        ``{**ctx, "key": value}`` or ``ctx.copy()``).
    description:
        Optional documentation string.

    Example::

        from ai_model.image.manipulation import sharpen
        step = Step(
            name="sharpen",
            fn=lambda ctx: {**ctx, "image": sharpen(ctx["image"])},
            description="Sharpen the image using unsharp mask.",
        )
    """

    name: str
    fn: Callable[[Dict[str, Any]], Dict[str, Any]]
    description: str = ""


class Workflow(ExtrovertAgent):
    """An ordered, composable pipeline of :class:`Step` objects.

    Parameters
    ----------
    name:
        Identifier for log messages.
    steps:
        Optional initial list of steps.

    Example::

        wf = Workflow("enhance")
        wf.add_step(Step("resize", lambda ctx: {**ctx, "image": resize(ctx["image"], 640, 480)}))
        result = wf.run({"image": my_image})
    """

    def __init__(
        self,
        name: str = "workflow",
        steps: Optional[List[Step]] = None,
    ) -> None:
        # Generate unique agent ID: workflow-XXXX
        agent_id = 'workflow-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        super().__init__(agent_id=agent_id)
        
        self.name = name
        self._steps: List[Step] = list(steps or [])
        self.start()

    # ------------------------------------------------------------------ #
    # building                                                             #
    # ------------------------------------------------------------------ #

    def add_step(self, step: Step) -> "Workflow":
        """Append *step* to the pipeline.

        Returns
        -------
        Workflow
            Self, for chaining.
        """
        self._steps.append(step)
        return self

    def prepend_step(self, step: Step) -> "Workflow":
        """Insert *step* at the beginning of the pipeline."""
        self._steps.insert(0, step)
        return self

    def steps(self) -> List[Step]:
        """Return a copy of the step list."""
        return list(self._steps)

    # ------------------------------------------------------------------ #
    # execution                                                            #
    # ------------------------------------------------------------------ #

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute all steps in order."""
        self.update_status(AgentStatus.WORKING)
        ctx = dict(context)
        logger.info("[%s] Starting (%d steps)", self.name, len(self._steps))

        for i, step in enumerate(self._steps, 1):
            logger.info("  [%d/%d] Running %s...", i, len(self._steps), step.name)
            self.coordinator.publish("STEP_START", step.name, {"workflow": self.name, "step_index": i})
            start_t = time.time()
            try:
                ctx = step.fn(ctx)
                if ctx is None:
                    raise RuntimeError(
                        f"Step {step.name!r} returned None.  "
                        "Each step must return the updated context dict."
                    )
            except Exception as e:
                self.update_status(AgentStatus.WAITING_FOR_INPUT)
                raise RuntimeError(f"Step '{step.name}' failed: {e}") from e
            
            elapsed = time.time() - start_t
            self.coordinator.publish("STEP_COMPLETE", step.name, {"workflow": self.name, "duration": elapsed})

        logger.info("[%s] Done.", self.name)
        self.update_status(AgentStatus.WAITING_FOR_INPUT)
        return ctx

    # ------------------------------------------------------------------ #
    # composition                                                          #
    # ------------------------------------------------------------------ #

    def __add__(self, other: "Workflow") -> "Workflow":
        """Concatenate two workflows into a new one.

        Example::

            combined = preprocess_wf + analysis_wf
        """
        return Workflow(
            name=f"{self.name}+{other.name}",
            steps=self._steps + other._steps,
        )

    def __repr__(self) -> str:
        step_names = [s.name for s in self._steps]
        return f"Workflow(name={self.name!r}, steps={step_names})"
