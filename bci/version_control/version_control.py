class EvaluationResult:
    BuildUnavailable = "build unavailable"
    Error = "error"
    Positive = "positive"
    Negative = "negative"
    Undefined = "undefined"


class RepoState:

    def __init__(self, state_id: str, parents=None, children=None):
        self.id: str = state_id
        self.parents = [] if parents is None else parents
        self.children = [] if children is None else children
        self.result = []
        self.evaluation_target = False

    def add_parent(self, new_parent):
        if not self.is_parent(new_parent):
            self.parents.append(new_parent)
        if not new_parent.is_child(self):
            new_parent.add_child(self)

    def add_child(self, new_child):
        if not self.is_child(new_child):
            self.children.append(new_child)
        if not new_child.is_parent(self):
            new_child.add_parent(self)

    def is_parent(self, parent):
        return parent in self.parents

    def is_child(self, child):
        return child in self.children

    def is_evaluation_target(self):
        return self.evaluation_target

    def set_as_evaluation_target(self):
        self.evaluation_target = True

    def set_evaluation_outcome(self, outcome: bool):
        if outcome:
            self.result = EvaluationResult.Positive
        else:
            self.result = EvaluationResult.Negative

    def set_evaluation_build_unavailable(self):
        self.result = EvaluationResult.BuildUnavailable

    def set_evaluation_error(self, error_message):
        self.result = error_message

    @property
    def build_unavailable(self):
        return self.result == EvaluationResult.BuildUnavailable

    @property
    def result_undefined(self):
        return len(self.result) == 0

    @classmethod
    def create_state_list(cls, evaluation_targets, changeset_id_list) -> list:
        states = []
        ancestor_state = cls(changeset_id_list[0])
        descendant_state = cls(changeset_id_list[len(changeset_id_list) - 1])

        states.append(ancestor_state)
        prev_state = ancestor_state
        for i in range(1, len(changeset_id_list) - 1):
            changeset_id = changeset_id_list[i]
            curr_state = cls(changeset_id)
            curr_state.add_parent(prev_state)
            states.append(curr_state)
            prev_state = curr_state
            if evaluation_targets is None or changeset_id in evaluation_targets:
                curr_state.set_as_evaluation_target()

        descendant_state.add_parent(prev_state)
        states.append(descendant_state)
        return states

    def __str__(self):
        return "%s: %s" % (str(self.id), self.result)

    def __repr__(self):
        return "%s: %s" % (str(self.id), self.result)


class RepoLineage:

    def __init__(self):
        self.ancestor_state = None
        self.descendant_state = None
        self.states = []

    @property
    def nb_of_states(self):
        return len(self.states)

    @property
    def nb_of_processed_states(self):
        return len([state for state in self.states if not state.result_undefined])

    @property
    def lower_state_id(self):
        return self.states[0].id

    @property
    def upper_state_id(self):
        return self.states[len(self.states) - 1].id

    @property
    def state_id_list(self):
        return [state.id for state in self.states]

    @property
    def state_ids_are_sequential(self):
        raise NotImplementedError("Cannot access abstract property")
