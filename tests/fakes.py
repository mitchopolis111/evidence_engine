from copy import deepcopy


class FakeWriteResult:
    def __init__(self, upserted_id=None, upserted_count=0, matched_count=0):
        self.upserted_id = upserted_id
        self.upserted_count = upserted_count
        self.matched_count = matched_count


class FakeCursor(list):
    def sort(self, fields):
        for field, direction in reversed(fields):
            super().sort(key=lambda document: document.get(field), reverse=direction < 0)
        return self


class FakeCollection:
    def __init__(self):
        self.documents = {}
        self.indexes = []

    @staticmethod
    def _key(query):
        return tuple(sorted((key, value) for key, value in query.items() if not isinstance(value, dict)))

    def create_index(self, fields, **options):
        self.indexes.append((fields, options))
        return options.get("name")

    def update_one(self, query, update, upsert=False):
        key = next(
            (
                stored_key
                for stored_key, document in self.documents.items()
                if self._matches(document, query)
            ),
            None,
        )
        if key is not None:
            self._apply_update(self.documents[key], update, inserted=False)
            return FakeWriteResult(matched_count=1)
        if not upsert:
            return FakeWriteResult()
        key = self._key(query)
        self.documents[key] = deepcopy(update["$setOnInsert"])
        self._apply_update(self.documents[key], update, inserted=True)
        return FakeWriteResult(upserted_id=str(len(self.documents)))

    def find_one(self, query, projection=None):
        document = self.documents.get(self._key(query))
        return self._project(document, projection)

    def find(self, query, projection=None):
        result = []
        for document in self.documents.values():
            if not self._matches(document, query):
                continue
            result.append(self._project(document, projection))
        return FakeCursor(result)

    def bulk_write(self, operations, ordered=False):
        upserted_count = 0
        matched_count = 0
        for operation in operations:
            key = next(
                (
                    stored_key
                    for stored_key, document in self.documents.items()
                    if self._matches(document, operation._filter)
                ),
                None,
            )
            inserted = False
            if key is None and operation._upsert:
                key = self._key(operation._filter)
                self.documents[key] = deepcopy(operation._doc["$setOnInsert"])
                upserted_count += 1
                inserted = True
            elif key is not None:
                matched_count += 1
            if key is not None:
                self._apply_update(self.documents[key], operation._doc, inserted)
        return FakeWriteResult(
            upserted_count=upserted_count,
            matched_count=matched_count,
        )

    @staticmethod
    def _apply_update(document, update, inserted):
        if inserted:
            document.update(deepcopy(update.get("$setOnInsert", {})))
        for field, value in update.get("$set", {}).items():
            document[field] = deepcopy(value)
        for field, value in update.get("$addToSet", {}).items():
            values = document.setdefault(field, [])
            if value not in values:
                values.append(deepcopy(value))
        for field, value in update.get("$inc", {}).items():
            document[field] = document.get(field, 0) + value

    @staticmethod
    def _matches(document, query):
        for field, expected in query.items():
            if isinstance(expected, dict) and "$in" in expected:
                if document.get(field) not in expected["$in"]:
                    return False
            elif document.get(field) != expected:
                return False
        return True

    @staticmethod
    def _project(document, projection):
        if document is None:
            return None
        result = deepcopy(document)
        if projection:
            included = {field for field, enabled in projection.items() if enabled and field != "_id"}
            if included:
                result = {field: result[field] for field in included if field in result}
            else:
                for field, enabled in projection.items():
                    if not enabled:
                        result.pop(field, None)
        return result
