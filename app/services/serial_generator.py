import secrets
from typing import Set, List
from app.models.product import SerializationProfile

class SerialGenerator:
    LOOKALIKE_CHARACTERS = {"0", "1", "I", "L", "O", "U"}

    @staticmethod
    def _validate_profile(profile: SerializationProfile) -> None:
        alphabet = profile.alphabet.upper()
        unique_chars = set(alphabet)
        blocked_chars = unique_chars.intersection(SerialGenerator.LOOKALIKE_CHARACTERS)

        if not alphabet:
            raise ValueError("Serialization alphabet cannot be empty.")
        if len(unique_chars) != len(alphabet):
            raise ValueError("Serialization alphabet cannot contain duplicate characters.")
        if blocked_chars:
            blocked = ", ".join(sorted(blocked_chars))
            raise ValueError(f"Serialization alphabet contains look-alike characters: {blocked}.")
        if profile.length < 1:
            raise ValueError("Serial length must be greater than zero.")
        if not profile.allow_duplicate_characters and profile.length > len(unique_chars):
            raise ValueError(
                f"Requested length {profile.length} is greater than unique character set size {len(unique_chars)} "
                "with unique-character serial generation enabled."
            )
        if profile.require_alpha and not any(c.isalpha() for c in alphabet):
            raise ValueError("Serialization alphabet must contain at least one letter.")
        if profile.require_numeric and not any(c.isdigit() for c in alphabet):
            raise ValueError("Serialization alphabet must contain at least one digit.")

        minimum_required_types = int(profile.require_alpha) + int(profile.require_numeric)
        if profile.length < minimum_required_types:
            raise ValueError("Serial length is too short for the required character rules.")

    @staticmethod
    def generate_single(profile: SerializationProfile) -> str:
        """Generates a single serial number meeting the profile rules."""
        SerialGenerator._validate_profile(profile)
        alphabet = profile.alphabet.upper()
        unique_chars = set(alphabet)
        length = profile.length
        allow_duplicates = (length > len(unique_chars))

        while True:
            candidate_chars = []
            if not allow_duplicates:
                # Select unique characters
                available = list(alphabet)
                for _ in range(length):
                    char = secrets.choice(available)
                    candidate_chars.append(char)
                    available.remove(char)
            else:
                candidate_chars = [secrets.choice(alphabet) for _ in range(length)]

            candidate = "".join(candidate_chars).upper()

            # Rule: Must contain both alpha and numeric characters
            has_alpha = any(c.isalpha() for c in candidate)
            has_numeric = any(c.isdigit() for c in candidate)

            if profile.require_alpha and not has_alpha:
                continue
            if profile.require_numeric and not has_numeric:
                continue

            return candidate

    @staticmethod
    def generate_batch(quantity: int, profile: SerializationProfile, existing_set: Set[str]) -> List[str]:
        """
        Generates a batch of unique serial strings.
        Ensures none of the newly generated serials collide with each other or with the existing set.
        """
        SerialGenerator._validate_profile(profile)
        if quantity < 1:
            raise ValueError("Batch quantity must be greater than zero.")

        alphabet = profile.alphabet.upper()
        length = profile.length
        require_alpha = profile.require_alpha
        require_numeric = profile.require_numeric
        sys_random = secrets.SystemRandom()

        generated_lookup: Set[str] = set()
        generated_serials: List[str] = []
        retries = 0
        max_retries = max(quantity * 20, 100)
        
        while len(generated_serials) < quantity:
            if retries > max_retries:
                raise RuntimeError(
                    f"Exceeded max retries ({max_retries}) during batch generation. "
                    "Alphabet or length constraints might be too restrictive."
                )
            
            # Fast C-optimized random character sampling
            if length <= len(alphabet):
                candidate = "".join(sys_random.sample(alphabet, length))
            else:
                candidate = "".join(sys_random.choices(alphabet, k=length))
            
            # Fast constraints evaluation
            if require_alpha:
                has_alpha = False
                for c in candidate:
                    if c.isalpha():
                        has_alpha = True
                        break
                if not has_alpha:
                    retries += 1
                    continue
                    
            if require_numeric:
                has_numeric = False
                for c in candidate:
                    if c.isdigit():
                        has_numeric = True
                        break
                if not has_numeric:
                    retries += 1
                    continue
            
            if candidate not in generated_lookup and candidate not in existing_set:
                generated_lookup.add(candidate)
                generated_serials.append(candidate)
            else:
                retries += 1

        return generated_serials
